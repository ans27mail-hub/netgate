import hashlib
import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import Redis
from rq import Queue
from sqlalchemy import Text, cast, func, or_, select
from starlette.middleware.sessions import SessionMiddleware

from .auth import PERM_KEYS, PERMS, ROLES, can, hash_password, sees_all_groups, verify_password
from .db import (FIELD_TYPES, Field, Group, Job, Keyword, Record, SessionLocal, User, UserGroup,
                 default_fields, init_db, slugify)
from .worker import run_job

BASE = os.path.dirname(__file__)
SECRET = os.environ.get("APP_SECRET_KEY") or hashlib.sha256(os.environ["DATABASE_URL"].encode()).hexdigest()

app = FastAPI(title="NetGate")
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax", max_age=14 * 24 * 3600)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))
queue = Queue("netgate", connection=Redis.from_url(os.environ["REDIS_URL"]))


# ---------- helpers ----------

class LoginRequired(Exception):
    pass


class Forbidden(Exception):
    pass


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc):
    with SessionLocal() as s:
        has_users = s.scalar(select(func.count(User.id)))
    return RedirectResponse("/login" if has_users else "/setup", status_code=303)


@app.exception_handler(Forbidden)
async def _forbidden(request: Request, exc):
    return HTMLResponse("<p style='font-family:sans-serif;padding:40px'>You don't have permission for this. "
                        "<a href='/'>Back to the directory</a></p>", status_code=403)


def fmt_value(record, field) -> str:
    v = (record.data or {}).get(field.key)
    if isinstance(v, list):
        return ", ".join(map(str, v)) or "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "—" if v in (None, "") else str(v)


def is_fresh(record) -> bool:
    """Updated (not just added) in the last 7 days."""
    if not record.updated_at or not record.created_at:
        return False
    return (record.updated_at - record.created_at > timedelta(minutes=1)
            and datetime.now() - record.updated_at < timedelta(days=7))


def domain(url: str) -> str:
    return url.split("//")[-1].split("/")[0].removeprefix("www.")


templates.env.globals.update(can=can, fmt=fmt_value, fresh=is_fresh, domain=domain, PERMS=PERMS,
                             FIELD_TYPES=FIELD_TYPES, ROLES=ROLES)


def current_user(s, request: Request) -> User:
    uid = request.session.get("uid")
    user = s.get(User, uid) if uid else None
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired
    return user


def require(user, perm, group_id=None):
    if not can(user, perm, group_id):
        raise Forbidden


def flash(request: Request, message: str, error: bool = False):
    request.session["flash"] = [message, error]


def go(url: str):
    return RedirectResponse(url, status_code=303)


def all_groups(s):
    return s.scalars(select(Group).order_by(Group.position, Group.id)).all()


def render(request: Request, s, user, name: str, **ctx):
    groups = all_groups(s)
    ctx.setdefault("sel_group", None)
    ctx.setdefault("q", "")
    ctx.setdefault("active_nav", None)
    ctx.setdefault("group", None)
    return templates.TemplateResponse(request, name, {
        "user": user,
        "groups": [g for g in groups if can(user, "view", g.id)],
        "req_groups": [g for g in groups if can(user, "request", g.id)],
        "flash": request.session.pop("flash", None),
        **ctx,
    })


def jobs_for(s, user, limit: int):
    stmt = select(Job).order_by(Job.id.desc()).limit(limit)
    if not sees_all_groups(user):
        stmt = stmt.where(or_(Job.group_id.in_(list(user.group_ids) or [-1]), Job.user_id == user.id))
    return s.scalars(stmt).all()


def enqueue(s, user, query: str, group_id: int, kind: str):
    job = Job(query=query, group_id=group_id, kind=kind, user_id=user.id)
    s.add(job)
    s.commit()
    queue.enqueue(run_job, job.id, job_timeout=3600)
    return job


@app.on_event("startup")
def startup():
    init_db()


# ---------- first run, login ----------

@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    with SessionLocal() as s:
        if s.scalar(select(func.count(User.id))):
            return go("/login")
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@app.post("/setup")
def setup(request: Request, username: str = Form(...), password: str = Form(...), password2: str = Form(...)):
    username = username.strip().lower()
    error = None
    if len(username) < 3:
        error = "Username needs at least 3 characters."
    elif len(password) < 8:
        error = "Password needs at least 8 characters."
    elif password != password2:
        error = "The two passwords don't match."
    with SessionLocal() as s:
        if s.scalar(select(func.count(User.id))):
            return go("/login")
        if error:
            return templates.TemplateResponse(request, "setup.html", {"error": error, "username": username})
        user = User(username=username, password_hash=hash_password(password), is_admin=True, role="Admin",
                    perms=",".join(PERM_KEYS), all_groups=True, active=True)
        s.add(user)
        s.commit()
        request.session["uid"] = user.id
    return go("/")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    with SessionLocal() as s:
        if not s.scalar(select(func.count(User.id))):
            return go("/setup")
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.username == username.strip().lower()))
        if not user or not user.active or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(request, "login.html",
                                              {"error": "Wrong username or password.", "username": username},
                                              status_code=401)
        request.session["uid"] = user.id
    return go("/")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/login")


# ---------- directory ----------

def _sort_key(field):
    choices = field.choice_list()

    def key(r):
        v = (r.data or {}).get(field.key)
        if isinstance(v, list):
            v = v[0] if v else None
        if v in (None, "", "Unknown"):
            return (1, 0.0, "")
        if field.type == "choice":
            return (0, float(choices.index(v)) if v in choices else float(len(choices)), "")
        if field.type == "number":
            try:
                return (0, float(v), "")
            except (TypeError, ValueError):
                return (1, 0.0, "")
        return (0, 0.0, str(v).lower())
    return key


@app.get("/", response_class=HTMLResponse)
def directory(request: Request, group: int | None = None, q: str = "", sort: str = "updated"):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        groups = [g for g in all_groups(s) if can(user, "view", g.id)]
        sel = next((g for g in groups if g.id == group), None)

        stmt = select(Record)
        if sel:
            stmt = stmt.where(Record.group_id == sel.id)
        elif not sees_all_groups(user):
            stmt = stmt.where(Record.group_id.in_([g.id for g in groups] or [-1]))
        if q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Record.title.ilike(like), Record.summary.ilike(like),
                                  Record.facts.ilike(like), cast(Record.data, Text).ilike(like)))

        fields = sel.fields if sel else []
        active = {}
        for f in fields:
            value = request.query_params.get(f"f_{f.key}", "")
            if f.filter and value:
                active[f.key] = value
                stmt = stmt.where(Record.data.contains({f.key: [value]} if f.type == "list" else {f.key: value}))
        records = s.scalars(stmt.order_by(Record.updated_at.desc()).limit(300)).all()

        if sort == "name":
            records.sort(key=lambda r: (r.title or "").lower())
        elif sort.startswith("f_"):
            field = next((f for f in fields if f.key == sort[2:] and f.sort), None)
            if field:
                records.sort(key=_sort_key(field))

        options = {}
        if sel:
            all_data = s.scalars(select(Record.data).where(Record.group_id == sel.id)).all()
            for f in fields:
                if not f.filter:
                    continue
                if f.type == "choice":
                    options[f.key] = f.choice_list() + ["Unknown"]
                    continue
                values = set()
                for d in all_data:
                    v = (d or {}).get(f.key)
                    for item in (v if isinstance(v, list) else [v]):
                        if item not in (None, ""):
                            values.add(str(item))
                options[f.key] = sorted(values, key=str.lower)[:300]

        group_names = {g.id: g.name for g in groups}
        return render(request, s, user, "directory.html", sel_group=sel, records=records, q=q, sort=sort,
                      fields=fields, active=active, options=options, group_names=group_names,
                      jobs=jobs_for(s, user, 8))


@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        return templates.TemplateResponse(request, "_activity.html", {"jobs": jobs_for(s, user, 8)})


@app.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        group_names = {g.id: g.name for g in all_groups(s)}
        return render(request, s, user, "requests.html", jobs=jobs_for(s, user, 100), group_names=group_names)


@app.post("/jobs")
def create_job(request: Request, query: str = Form(...), group_id: int = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "request", group_id)
        if not s.get(Group, group_id) or not query.strip():
            flash(request, "Choose a group and describe what to look for.", True)
            return go("/")
        enqueue(s, user, query.strip(), group_id, "request")
        flash(request, "Request sent to the AI. Watch its progress under AI activity.")
    return go(f"/?group={group_id}")


@app.post("/groups/{gid}/keywords/{kid}/run")
def run_keyword(request: Request, gid: int, kid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            enqueue(s, user, kw.text, gid, "keyword")
            flash(request, f"Updating \"{kw.text}\". Watch its progress under AI activity.")
    return go(f"/?group={gid}")


@app.post("/groups/{gid}/keywords/run-all")
def run_all_keywords(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        group = s.get(Group, gid)
        for kw in (group.keywords if group else []):
            enqueue(s, user, kw.text, gid, "keyword")
        flash(request, f"Queued {len(group.keywords) if group else 0} keyword update(s).")
    return go(f"/?group={gid}")


@app.post("/records/{rid}/delete")
def delete_record(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec:
            return go("/")
        require(user, "delete", rec.group_id)
        gid = rec.group_id
        s.delete(rec)
        s.commit()
        flash(request, "Listing deleted.")
    return go(f"/?group={gid}" if gid else "/")


# ---------- settings: groups ----------

@app.get("/settings")
def settings_home(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        if can(user, "manage_groups"):
            return go("/settings/groups")
        if can(user, "manage_users"):
            return go("/settings/users")
    raise Forbidden


@app.get("/settings/groups", response_class=HTMLResponse)
def groups_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        groups = all_groups(s)
        if groups:
            return go(f"/settings/groups/{groups[0].id}")
        return render(request, s, user, "group_edit.html", all=groups, group=None)


@app.post("/settings/groups")
def create_group(request: Request, name: str = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        name = name.strip()
        if not name or s.scalar(select(Group).where(Group.name == name)):
            flash(request, "Give the group a new, unique name.", True)
            return go("/settings/groups")
        position = (s.scalar(select(func.max(Group.position))) or 0) + 1
        group = Group(name=name, position=position)
        group.fields = default_fields()
        s.add(group)
        s.commit()
        flash(request, f"Group \"{name}\" created. Add keywords and fields below.")
        return go(f"/settings/groups/{group.id}")


@app.get("/settings/groups/{gid}", response_class=HTMLResponse)
def group_edit(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        if not group:
            return go("/settings/groups")
        count = s.scalar(select(func.count(Record.id)).where(Record.group_id == gid))
        return render(request, s, user, "group_edit.html", all=all_groups(s), group=group, count=count)


@app.post("/settings/groups/{gid}")
def group_save(request: Request, gid: int, name: str = Form(...), instructions: str = Form(""),
               search_terms: str = Form(""), position: int = Form(0)):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        clash = s.scalar(select(Group).where(Group.name == name.strip(), Group.id != gid))
        if group and name.strip() and not clash:
            group.name, group.instructions = name.strip(), instructions.strip()
            group.search_terms, group.position = search_terms.strip(), position
            s.commit()
            flash(request, "Group saved.")
        else:
            flash(request, "That name is empty or already used.", True)
    return go(f"/settings/groups/{gid}")


@app.post("/settings/groups/{gid}/delete")
def group_delete(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        if group:
            s.delete(group)
            s.commit()
            flash(request, f"Group \"{group.name}\" and its listings were deleted.")
    return go("/settings/groups")


@app.post("/settings/groups/{gid}/keywords")
def keyword_add(request: Request, gid: int, text: str = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        existing = {k.text.lower() for k in group.keywords}
        for part in text.replace("\n", ",").split(","):
            part = part.strip()
            if part and part.lower() not in existing:
                group.keywords.append(Keyword(text=part))
                existing.add(part.lower())
        s.commit()
    return go(f"/settings/groups/{gid}#keywords")


@app.post("/settings/groups/{gid}/keywords/{kid}/delete")
def keyword_delete(request: Request, gid: int, kid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            s.delete(kw)
            s.commit()
    return go(f"/settings/groups/{gid}#keywords")


@app.post("/settings/groups/{gid}/fields")
def field_add(request: Request, gid: int, name: str = Form(...), type: str = Form("text"), choices: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        name = name.strip()
        if not name:
            return go(f"/settings/groups/{gid}#fields")
        key, taken, n = slugify(name), {f.key for f in group.fields}, 2
        base = key
        while key in taken:
            key, n = f"{base}_{n}", n + 1
        position = max([f.position for f in group.fields] or [0]) + 1
        group.fields.append(Field(name=name, key=key, type=type if type in FIELD_TYPES else "text",
                                  choices=choices.strip(), position=position, card=True))
        s.commit()
        flash(request, f"Field \"{name}\" added. The AI fills it on the next update.")
    return go(f"/settings/groups/{gid}#fields")


@app.post("/settings/groups/{gid}/fields/{fid}")
def field_save(request: Request, gid: int, fid: int, name: str = Form(...), type: str = Form("text"),
               choices: str = Form(""), filter: str = Form(""), sort: str = Form(""), card: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        f = s.get(Field, fid)
        if f and f.group_id == gid and name.strip():
            f.name, f.type, f.choices = name.strip(), type if type in FIELD_TYPES else "text", choices.strip()
            f.filter, f.sort, f.card = bool(filter), bool(sort), bool(card)
            s.commit()
            flash(request, f"Field \"{f.name}\" saved.")
    return go(f"/settings/groups/{gid}#fields")


@app.post("/settings/groups/{gid}/fields/{fid}/delete")
def field_delete(request: Request, gid: int, fid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        f = s.get(Field, fid)
        if f and f.group_id == gid:
            s.delete(f)
            s.commit()
    return go(f"/settings/groups/{gid}#fields")


# ---------- settings: users ----------

@app.get("/settings/users", response_class=HTMLResponse)
def users_page(request: Request):
    return _user_page(request, None)


@app.get("/settings/users/{uid}", response_class=HTMLResponse)
def user_page(request: Request, uid: int):
    return _user_page(request, uid)


def _user_page(request: Request, uid: int | None):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_users")
        users = s.scalars(select(User).order_by(User.is_admin.desc(), User.username)).all()
        edit = s.get(User, uid) if uid else None
        group_names = {g.id: g.name for g in all_groups(s)}
        return render(request, s, user, "users.html", users=users, edit=edit, all=all_groups(s),
                      group_names=group_names, group=None, active_nav="users")


@app.post("/settings/users/new")
async def user_create(request: Request):
    return await _user_save(request, None)


@app.post("/settings/users/{uid}")
async def user_update(request: Request, uid: int):
    return await _user_save(request, uid)


async def _user_save(request: Request, uid: int | None):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    role = str(form.get("role", "Viewer"))
    role = role if role in ("Admin", "Editor", "Viewer", "Custom") else "Viewer"
    perms = [p for p in form.getlist("perms") if p in PERM_KEYS]
    all_grp = form.get("access") != "some"
    group_ids = {int(g) for g in form.getlist("groups") if str(g).isdigit()}
    active = form.get("active") == "on"

    with SessionLocal() as s:
        me = current_user(s, request)
        require(me, "manage_users")
        back = f"/settings/users/{uid}" if uid else "/settings/users"
        target = s.get(User, uid) if uid else None
        if uid and not target:
            return go("/settings/users")
        if len(username) < 3:
            flash(request, "Username needs at least 3 characters.", True)
            return go(back)
        if s.scalar(select(User).where(User.username == username, User.id != (uid or 0))):
            flash(request, "That username is already taken.", True)
            return go(back)
        if (not target or password) and len(password) < 8:
            flash(request, "Password needs at least 8 characters.", True)
            return go(back)
        if role == "Admin" and not me.is_admin:
            flash(request, "Only an admin can make someone an admin.", True)
            return go(back)
        # never lock everyone out: keep at least one active admin
        if target and target.is_admin and (role != "Admin" or not active):
            others = s.scalar(select(func.count(User.id)).where(User.is_admin, User.active, User.id != target.id))
            if not others:
                flash(request, "This is the last active admin, so it must stay an active admin.", True)
                return go(back)

        target = target or User(password_hash="")
        target.username, target.role, target.active = username, role, active if uid else True
        target.is_admin = role == "Admin"
        target.perms = ",".join(PERM_KEYS if target.is_admin else perms)
        target.all_groups = target.is_admin or all_grp
        target.group_links = [] if target.all_groups else [UserGroup(group_id=g) for g in sorted(group_ids)]
        if password:
            target.password_hash = hash_password(password)
        s.add(target)
        s.commit()
        flash(request, f"User \"{username}\" saved.")
        return go(f"/settings/users/{target.id}")


@app.get("/health")
def health():
    return {"ok": True}
