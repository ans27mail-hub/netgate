import csv
import hashlib
import io
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import Redis
from rq import Queue
from sqlalchemy import Text, cast, func, or_, select
from starlette.middleware.sessions import SessionMiddleware

from . import ai, crawl
from .auth import PERM_KEYS, PERMS, ROLES, can, hash_password, sees_all_groups, verify_password
from .db import (FIELD_TYPES, AIServer, Field, Group, Job, Keyword, NightRun, PageCache, Record, SessionLocal,
                 User, UserGroup, default_fields, get_setting, init_db, set_setting, slugify)
from .jobs import (NIGHT_DEFAULTS, Ctx, _ask_entries, _enhance_entries, completeness, empty, night_settings,
                   run_job)

VERSION = "v0.4"
BASE = os.path.dirname(__file__)
SECRET = os.environ.get("APP_SECRET_KEY") or hashlib.sha256(os.environ["DATABASE_URL"].encode()).hexdigest()

app = FastAPI(title="NetGate")
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax", max_age=14 * 24 * 3600)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))
queue = Queue("netgate", connection=Redis.from_url(os.environ["REDIS_URL"]))

DISPLAY_DEFAULTS = {"mode": "fixed", "px": 1280, "pct": 90, "view": "grid", "per_row": 0}
SPECIAL_COLS = {"_complete": "Complete", "_updated": "Updated"}


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
            and datetime.utcnow() - record.updated_at < timedelta(days=7))


def domain(url: str) -> str:
    return (url or "").split("//")[-1].split("/")[0].removeprefix("www.")


def ago(dt) -> str:
    if not dt:
        return "never"
    secs = (datetime.utcnow() - dt).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    days = int(secs // 86400)
    return "yesterday" if days == 1 else f"{days} days ago"


templates.env.globals.update(can=can, fmt=fmt_value, fresh=is_fresh, domain=domain, ago=ago, empty=empty,
                             completeness=completeness, PERMS=PERMS, FIELD_TYPES=FIELD_TYPES, ROLES=ROLES,
                             VERSION=VERSION, SPECIAL_COLS=SPECIAL_COLS, JOB_TYPES=ai.JOB_TYPES)


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


def back(request: Request, default: str = "/"):
    ref = request.headers.get("referer") or ""
    host = request.headers.get("host") or ""
    return go(ref if host and f"//{host}/" in ref else default)


def all_groups(s):
    return s.scalars(select(Group).order_by(Group.position, Group.id)).all()


def display_for(s, user) -> dict:
    d = {**DISPLAY_DEFAULTS, **(get_setting(s, "display", {}) or {})}
    d.update((user.prefs or {}).get("display") or {})
    return d


def page_style(d: dict) -> str:
    if d["mode"] == "full":
        return "--wrap-max:none;--wrap-w:100%"
    if d["mode"] == "pct":
        pct = min(100, max(50, int(d.get("pct") or 90)))
        return f"--wrap-max:none;--wrap-w:{pct}%"
    return f"--wrap-max:{min(3000, max(800, int(d.get('px') or 1280)))}px;--wrap-w:100%"


def render(request: Request, s, user, name: str, **ctx):
    groups = all_groups(s)
    for key, default in (("sel_group", None), ("q", ""), ("active_nav", None), ("group", None)):
        ctx.setdefault(key, default)
    d = display_for(s, user)
    return templates.TemplateResponse(request, name, {
        "user": user,
        "groups": [g for g in groups if can(user, "view", g.id)],
        "req_groups": [g for g in groups if can(user, "request", g.id)],
        "flash": request.session.pop("flash", None),
        "display": d,
        "page_style": page_style(d),
        **ctx,
    })


def jobs_for(s, user, limit: int):
    stmt = select(Job).order_by(Job.id.desc()).limit(limit)
    if not sees_all_groups(user):
        stmt = stmt.where(or_(Job.group_id.in_(list(user.group_ids) or [-1]), Job.user_id == user.id))
    return s.scalars(stmt).all()


def enqueue(s, user, kind: str, query: str, group_id: int | None, record_id: int | None = None,
            keyword_id: int | None = None):
    job = Job(query=query, group_id=group_id, kind=kind, user_id=user.id, record_id=record_id, stats={})
    s.add(job)
    s.commit()
    queue.enqueue(run_job, job.id, keyword_id=keyword_id, job_timeout=3 * 3600)
    return job


def last_night(s):
    run = s.scalar(select(NightRun).order_by(NightRun.id.desc()).limit(1))
    if run and run.started_at and datetime.utcnow() - run.started_at < timedelta(hours=36):
        return run
    return None


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
                    perms=",".join(PERM_KEYS), all_groups=True, active=True, prefs={})
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
        if empty(v):
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


def _query_records(s, user, request: Request, sel, groups, q: str, sort: str, complete: str):
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
    records = s.scalars(stmt.order_by(Record.updated_at.desc()).limit(500)).all()

    by_group = {g.id: g for g in groups}
    if complete in ("missing", "complete"):
        def is_complete(r):
            filled, total = completeness(r, by_group.get(r.group_id))
            return filled >= total
        records = [r for r in records if is_complete(r) == (complete == "complete")]
    if sort == "name":
        records.sort(key=lambda r: (r.title or "").lower())
    elif sort == "least":
        records.sort(key=lambda r: completeness(r, by_group.get(r.group_id))[0])
    elif sort.startswith("f_"):
        field = next((f for f in fields if f.key == sort[2:] and f.sort), None)
        if field:
            records.sort(key=_sort_key(field))
    return records, fields, active


def _filter_options(s, sel):
    options = {}
    if not sel:
        return options
    all_data = s.scalars(select(Record.data).where(Record.group_id == sel.id)).all()
    for f in sel.fields:
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
    return options


def list_columns(user, sel) -> list[str]:
    if not sel:
        return ["_complete", "_updated"]
    saved = ((user.prefs or {}).get("cols") or {}).get(str(sel.id))
    keys = {f.key for f in sel.fields} | set(SPECIAL_COLS)
    if saved:
        return [c for c in saved if c in keys]
    return [f.key for f in sel.fields if f.list] + ["_complete", "_updated"]


@app.get("/", response_class=HTMLResponse)
def directory(request: Request, group: int | None = None, q: str = "", sort: str = "updated",
              view: str = "", complete: str = "any"):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        groups = [g for g in all_groups(s) if can(user, "view", g.id)]
        sel = next((g for g in groups if g.id == group), None)
        d = display_for(s, user)
        if view in ("grid", "list") and (user.prefs or {}).get("view") != view:
            user.prefs = {**(user.prefs or {}), "view": view}   # remember the last view per user
            s.commit()
        view = view if view in ("grid", "list") else ((user.prefs or {}).get("view") or d["view"])
        records, fields, active = _query_records(s, user, request, sel, groups, q, sort, complete)
        by_group = {g.id: g for g in groups}
        stats = None
        if sel:
            all_recs = s.scalars(select(Record).where(Record.group_id == sel.id)).all()
            done = sum(1 for r in all_recs if completeness(r, sel)[0] >= completeness(r, sel)[1])
            missing = sum(completeness(r, sel)[1] - completeness(r, sel)[0] for r in all_recs)
            stats = {"total": len(all_recs), "complete": done, "missing": missing,
                     "pct": int(done * 100 / len(all_recs)) if all_recs else 0}
        counts = dict(s.execute(select(Record.group_id, func.count(Record.id)).group_by(Record.group_id)).all())
        params = ([("group", sel.id)] if sel else []) + ([("q", q)] if q else []) \
            + [(f"f_{k}", v) for k, v in active.items()] + ([("complete", complete)] if complete != "any" else [])
        base_qs = urlencode(params) + ("&" if params else "")
        return render(request, s, user, "directory.html", sel_group=sel, records=records, q=q, sort=sort,
                      base_qs=base_qs,
                      complete=complete, view=view, fields=fields, active=active,
                      options=_filter_options(s, sel), by_group=by_group, counts=counts, stats=stats,
                      cols=list_columns(user, sel), jobs=jobs_for(s, user, 8), night=last_night(s),
                      night_cfg=night_settings(s))


@app.get("/records/{rid}/open", response_class=HTMLResponse)
def open_card(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec or not can(user, "view", rec.group_id):
            raise Forbidden
        group = s.get(Group, rec.group_id) if rec.group_id else None
        return templates.TemplateResponse(request, "_bigcard.html", {"r": rec, "g": group, "user": user})


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
        return render(request, s, user, "requests.html", jobs=jobs_for(s, user, 150), group_names=group_names)


@app.post("/jobs")
def create_job(request: Request, query: str = Form(...), group_id: int = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "request", group_id)
        if not s.get(Group, group_id) or not query.strip():
            flash(request, "Choose a group and describe what to look for.", True)
            return go("/")
        enqueue(s, user, "request", query.strip(), group_id)
        flash(request, "Search started. New companies appear as they are found — see AI activity.")
    return go(f"/?group={group_id}")


@app.post("/groups/{gid}/keywords/{kid}/run")
def run_keyword(request: Request, gid: int, kid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            enqueue(s, user, "keyword", kw.text, gid, keyword_id=kw.id)
            flash(request, f"Discovering “{kw.text}”. Watch AI activity.")
    return back(request, f"/?group={gid}")


@app.post("/groups/{gid}/keywords/run-all")
def run_all_keywords(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        group = s.get(Group, gid)
        for kw in (group.keywords if group else []):
            enqueue(s, user, "keyword", kw.text, gid, keyword_id=kw.id)
        flash(request, f"Queued {len(group.keywords) if group else 0} keyword search(es).")
    return go(f"/?group={gid}")


def _enrich_many(s, user, ids: list[int]) -> int:
    n = 0
    for rid in ids:
        rec = s.get(Record, rid)
        if rec and can(user, "request", rec.group_id):
            enqueue(s, user, "enrich", rec.title, rec.group_id, record_id=rec.id)
            n += 1
    return n


@app.post("/records/{rid}/enrich")
def enrich_one(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        n = _enrich_many(s, user, [rid])
        if not n:
            raise Forbidden
        flash(request, "Enrich started. The card updates when it finishes — see AI activity.")
    return back(request)


@app.post("/records/enrich-selected")
async def enrich_selected(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:100]
    with SessionLocal() as s:
        user = current_user(s, request)
        n = _enrich_many(s, user, ids)
        flash(request, f"Enrich started for {n} compan{'y' if n == 1 else 'ies'}." if n else
              "Tick one or more companies first.", not n)
    return back(request)


@app.post("/groups/{gid}/enrich-incomplete")
def enrich_incomplete(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "request", gid)
        group = s.get(Group, gid)
        recs = s.scalars(select(Record).where(Record.group_id == gid)).all()
        todo = sorted((completeness(r, group)[0], r.id) for r in recs
                      if completeness(r, group)[0] < completeness(r, group)[1])
        n = _enrich_many(s, user, [rid for _, rid in todo[:50]])
        flash(request, f"Enrich started for {n} incomplete compan{'y' if n == 1 else 'ies'}"
                       + (" (the 50 least complete; the rest can run tonight)." if len(todo) > 50 else "."))
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


@app.post("/prefs/view")
def pref_view(request: Request, view: str = Form("grid")):
    with SessionLocal() as s:
        user = current_user(s, request)
        user.prefs = {**(user.prefs or {}), "view": "list" if view == "list" else "grid"}
        s.commit()
    return back(request)


@app.post("/prefs/columns")
async def pref_columns(request: Request):
    form = await request.form()
    gid = str(form.get("group_id", ""))
    with SessionLocal() as s:
        user = current_user(s, request)
        cols = dict((user.prefs or {}).get("cols") or {})
        if form.get("reset"):
            cols.pop(gid, None)
        else:
            cols[gid] = [c for c in form.getlist("cols") if c]
        user.prefs = {**(user.prefs or {}), "cols": cols}
        s.commit()
    return back(request)


@app.get("/export.csv")
def export_csv(request: Request, group: int | None = None, q: str = "", sort: str = "updated",
               complete: str = "any"):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        groups = [g for g in all_groups(s) if can(user, "view", g.id)]
        sel = next((g for g in groups if g.id == group), None)
        records, fields, _ = _query_records(s, user, request, sel, groups, q, sort, complete)
        names = {g.id: g.name for g in groups}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Company", "Group"] + [f.name for f in fields] + ["Description", "Facebook", "Instagram",
                                                                      "LinkedIn", "First found on", "Updated"])
        for r in records:
            w.writerow([r.title, names.get(r.group_id, "")] + [fmt_value(r, f) for f in fields]
                       + [r.summary, (r.social or {}).get("facebook", ""), (r.social or {}).get("instagram", ""),
                          (r.social or {}).get("linkedin", ""), r.source_url,
                          r.updated_at.strftime("%Y-%m-%d") if r.updated_at else ""])
    fname = f"netgate-{slugify(sel.name) if sel else 'all'}.csv"
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


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
        return render(request, s, user, "group_edit.html", all=groups, group=None, counts={})


def _group_page(request, s, user, group, **extra):
    counts = dict(s.execute(select(Record.group_id, func.count(Record.id)).group_by(Record.group_id)).all())
    return render(request, s, user, "group_edit.html", all=all_groups(s), group=group,
                  count=counts.get(group.id, 0), counts=counts, **extra)


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
        flash(request, f"Group “{name}” created. Add keywords, instructions and fields below.")
        return go(f"/settings/groups/{group.id}")


@app.get("/settings/groups/{gid}", response_class=HTMLResponse)
def group_edit(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        if not group:
            return go("/settings/groups")
        return _group_page(request, s, user, group)


@app.post("/settings/groups/{gid}")
async def group_save(request: Request, gid: int):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        clash = s.scalar(select(Group).where(Group.name == name, Group.id != gid))
        if not group or not name or clash:
            flash(request, "That name is empty or already used.", True)
            return go(f"/settings/groups/{gid}")
        group.name = name
        group.position = int(form.get("position") or 0) if str(form.get("position", "0")).lstrip("-").isdigit() else 0
        group.instructions = str(form.get("instructions", "")).strip()
        group.enrich_instructions = str(form.get("enrich_instructions", "")).strip()
        group.ignore_instructions = str(form.get("ignore_instructions", "")).strip()
        group.search_terms = str(form.get("search_terms", "")).strip()
        s.commit()
        flash(request, "Group saved.")
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
            flash(request, f"Group “{group.name}” and its listings were deleted.")
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
                group.keywords.append(Keyword(text=part, night=True, found_count=0))
                existing.add(part.lower())
        s.commit()
    return go(f"/settings/groups/{gid}#keywords")


@app.post("/settings/groups/{gid}/keywords/{kid}/night")
def keyword_night(request: Request, gid: int, kid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            kw.night = not kw.night
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
def field_add(request: Request, gid: int, name: str = Form(...), type: str = Form("text"),
              choices: str = Form(""), words: str = Form(""), stage: str = Form("enrich")):
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
                                  choices=choices.strip(), words=words.strip(),
                                  stage="discover" if stage == "discover" else "enrich",
                                  position=position, card=False, list=True))
        s.commit()
        flash(request, f"Field “{name}” added. Enrich will look for it next time.")
    return go(f"/settings/groups/{gid}#fields")


@app.post("/settings/groups/{gid}/fields/{fid}")
def field_save(request: Request, gid: int, fid: int, name: str = Form(...), type: str = Form("text"),
               choices: str = Form(""), words: str = Form(""), stage: str = Form("enrich"),
               filter: str = Form(""), sort: str = Form(""), card: str = Form(""), list: str = Form(""),
               position: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        f = s.get(Field, fid)
        if f and f.group_id == gid and name.strip():
            f.name, f.type, f.choices = name.strip(), type if type in FIELD_TYPES else "text", choices.strip()
            f.words, f.stage = words.strip(), "discover" if stage == "discover" else "enrich"
            f.filter, f.sort, f.card, f.list = bool(filter), bool(sort), bool(card), bool(list)
            if position.lstrip("-").isdigit():
                f.position = int(position)
            s.commit()
            flash(request, f"Field “{f.name}” saved.")
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


@app.post("/settings/groups/{gid}/test", response_class=HTMLResponse)
def group_test(request: Request, gid: int, url: str = Form(...), query: str = Form("")):
    """Show what Discover would save from one page, with the current instructions. Saves nothing."""
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        group = s.get(Group, gid)
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        _ = group.fields
    # same steps as a real Discover: read the page (browser if needed), AI, then code-first details
    page = crawl.get_page(url, use_cache=False)
    result, error, info = None, None, ""
    if not page.ok:
        error = f"Could not read that page ({page.note or 'blocked, empty or not HTML'})."
    else:
        ctx = Ctx(None, "discover")
        try:
            result = _ask_entries(ctx, group, query or group.name, page)
            if result:
                _enhance_entries(ctx, page, result)
            nxt = crawl.next_page_url(page.html, page.final_url or url) if result and len(result) >= 3 else None
            info = ("Read with the browser. " if page.rendered else "") \
                + (f"{ctx.stats['profiles']} profile pages opened. " if ctx.stats["profiles"] else "") \
                + (f"Next page found: {nxt}" if nxt else "")
            for e in result:
                found = e.pop("_found", None) or {}
                e.pop("_found_url", None)
                e.pop("_own_site", None)
                e["code"] = ", ".join(x for x in [
                    (found.get("emails") or [None])[0], (found.get("phones") or [None])[0],
                    ", ".join(sorted((found.get("social") or {}).keys())) or None] if x)
        except Exception as e:
            error = f"AI error: {type(e).__name__}: {e}"
    with SessionLocal() as s:
        user = current_user(s, request)
        group = s.get(Group, gid)
        return _group_page(request, s, user, group,
                           test={"url": url, "entries": result, "error": error, "info": info})


# ---------- settings: AI servers ----------

@app.get("/settings/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        servers = s.scalars(select(AIServer).order_by(AIServer.id)).all()
        models = {sv.id: ai.list_models(sv) for sv in servers if sv.enabled}
        jobs = {j: get_setting(s, f"ai.{j}", {}) or {} for j in list(ai.JOB_TYPES) + ["fallback"]}
        now = datetime.utcnow()
        spend = {"day": ai.spent(s, now - timedelta(hours=24)),
                 "month": ai.spent(s, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))}
        return render(request, s, user, "ai.html", all=all_groups(s), active_nav="ai", servers=servers,
                      models=models, jobs=jobs, limits=get_setting(s, "ai.limits", {}) or {}, spend=spend)


@app.post("/settings/ai/servers")
def ai_server_add(request: Request, name: str = Form(...), kind: str = Form("ollama"), url: str = Form(""),
                  api_key: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        kind = "openrouter" if kind == "openrouter" else "ollama"
        if kind == "ollama" and not url.strip():
            flash(request, "Enter the server address, e.g. http://192.168.1.60:11434", True)
            return go("/settings/ai")
        s.add(AIServer(name=name.strip() or ("OpenRouter" if kind == "openrouter" else "Ollama"), kind=kind,
                       url=url.strip() if kind == "ollama" else "", api_key=api_key.strip(), enabled=True))
        s.commit()
        flash(request, "Server added. Choose it for a job below, then press Test.")
    return go("/settings/ai")


@app.post("/settings/ai/servers/{sid}")
def ai_server_save(request: Request, sid: int, name: str = Form(...), url: str = Form(""), api_key: str = Form(""),
                   enabled: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        sv = s.get(AIServer, sid)
        if sv:
            sv.name, sv.enabled = name.strip() or sv.name, bool(enabled)
            if sv.kind == "ollama":
                sv.url = url.strip() or sv.url
            if api_key.strip():
                sv.api_key = api_key.strip()
            s.commit()
            flash(request, f"{sv.name} saved.")
    return go("/settings/ai")


@app.post("/settings/ai/servers/{sid}/delete")
def ai_server_delete(request: Request, sid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        sv = s.get(AIServer, sid)
        in_use = [j for j in list(ai.JOB_TYPES) + ["fallback"] if (get_setting(s, f"ai.{j}", {}) or {}).get("server") == sid]
        if sv and in_use:
            flash(request, f"{sv.name} is still used for: {', '.join(in_use)}. Choose another server first.", True)
        elif sv:
            s.delete(sv)
            s.commit()
            flash(request, "Server removed.")
    return go("/settings/ai")


@app.post("/settings/ai/servers/{sid}/test")
def ai_server_test(request: Request, sid: int, model: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        sv = s.get(AIServer, sid)
        if not sv:
            return go("/settings/ai")
        model = model.strip()
        if not model:
            for j in ai.JOB_TYPES:
                conf = get_setting(s, f"ai.{j}", {}) or {}
                if conf.get("server") == sid:
                    model = conf.get("model", "")
                    break
        if not model:
            ms = ai.list_models(sv)
            model = ms[0]["id"] if ms else ""
        if not model:
            flash(request, f"{sv.name}: no models found — is the address right and the server running?", True)
            return go("/settings/ai")
    ok, msg = ai.test_server(sv, model)
    flash(request, f"{sv.name}: {msg}", not ok)
    return go("/settings/ai")


@app.post("/settings/ai/jobs")
async def ai_jobs_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        for j in list(ai.JOB_TYPES) + ["fallback"]:
            sid, model = str(form.get(f"{j}_server", "")), str(form.get(f"{j}_model", "")).strip()
            if sid.isdigit() and model:
                set_setting(s, f"ai.{j}", {"server": int(sid), "model": model})

        def num(key):
            try:
                return max(0.0, float(form.get(key) or 0))
            except ValueError:
                return 0.0
        set_setting(s, "ai.limits", {"night": num("limit_night"), "month": num("limit_month")})
        s.commit()
        flash(request, "AI settings saved.")
    return go("/settings/ai")


# ---------- settings: night jobs ----------

@app.get("/settings/night", response_class=HTMLResponse)
def night_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        runs = s.scalars(select(NightRun).order_by(NightRun.id.desc()).limit(10)).all()
        return render(request, s, user, "night.html", all=all_groups(s), active_nav="night",
                      cfg=night_settings(s), runs=runs)


@app.post("/settings/night")
async def night_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")

        def hhmm(v, default):
            v = str(v or "").strip()
            try:
                h, m = v.split(":")
                return f"{int(h) % 24:02d}:{int(m) % 60:02d}"
            except ValueError:
                return default

        def integer(v, default, lo, hi):
            try:
                return min(hi, max(lo, int(float(v))))
            except (TypeError, ValueError):
                return default
        cfg = {
            "enabled": form.get("enabled") == "on",
            "start": hhmm(form.get("start"), NIGHT_DEFAULTS["start"]),
            "stop": hhmm(form.get("stop"), NIGHT_DEFAULTS["stop"]),
            "days": [int(d) for d in form.getlist("days") if str(d).isdigit()],
            "max_companies": integer(form.get("max_companies"), 150, 0, 5000),
            "pause": integer(form.get("pause"), 3, 0, 120),
            "timezone": str(form.get("timezone") or "Asia/Karachi").strip(),
        }
        set_setting(s, "night", cfg)
        for g in all_groups(s):
            g.night_discover = form.get(f"d_{g.id}") == "on"
            g.night_enrich = form.get(f"e_{g.id}") == "on"
            g.refresh_days = integer(form.get(f"r_{g.id}"), 0, 0, 3650)
        s.commit()
        flash(request, "Night jobs saved." + ("" if cfg["enabled"] else " (Night jobs are switched off.)"))
    return go("/settings/night")


# ---------- settings: display ----------

@app.get("/settings/display", response_class=HTMLResponse)
def display_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        everyone = {**DISPLAY_DEFAULTS, **(get_setting(s, "display", {}) or {})}
        mine = (user.prefs or {}).get("display") or {}
        return render(request, s, user, "display.html", all=all_groups(s), active_nav="display",
                      everyone=everyone, mine=mine, current={**everyone, **mine})


@app.post("/settings/display")
async def display_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)

        def integer(v, default, lo, hi):
            try:
                return min(hi, max(lo, int(float(v))))
            except (TypeError, ValueError):
                return default
        d = {"mode": form.get("mode") if form.get("mode") in ("fixed", "pct", "full") else "fixed",
             "px": integer(form.get("px"), 1280, 800, 3000), "pct": integer(form.get("pct"), 90, 50, 100),
             "view": "list" if form.get("view") == "list" else "grid",
             "per_row": integer(form.get("per_row"), 0, 0, 8)}
        if form.get("scope") == "everyone" and can(user, "manage_groups"):
            set_setting(s, "display", d)
            prefs = dict(user.prefs or {})
            prefs.pop("display", None)
            user.prefs = prefs
            msg = "Display saved for everyone."
        else:
            user.prefs = {**(user.prefs or {}), "display": d}
            msg = "Display saved for you."
        s.commit()
        flash(request, msg)
    return go("/settings/display")


# ---------- settings: crawler ----------

@app.get("/settings/crawler", response_class=HTMLResponse)
def crawler_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        cfg = {**crawl.CRAWLER_DEFAULTS, **(get_setting(s, "crawler", {}) or {})}
        cache_rows = s.scalar(select(func.count(PageCache.url)))
        renderer_ok = crawl.renderer_status()
        return render(request, s, user, "crawler.html", all=all_groups(s), active_nav="crawler", cfg=cfg,
                      cache_rows=cache_rows, renderer_ok=renderer_ok)


@app.post("/settings/crawler")
async def crawler_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")

        def num(key, default, lo, hi, cast=int):
            try:
                return min(hi, max(lo, cast(float(form.get(key)))))
            except (TypeError, ValueError):
                return default
        d = crawl.CRAWLER_DEFAULTS
        cfg = {
            "render": form.get("render") if form.get("render") in ("auto", "never", "always") else "auto",
            "render_domains": str(form.get("render_domains") or "").strip(),
            "skip_domains": str(form.get("skip_domains") or "").strip(),
            "next_pages": num("next_pages", d["next_pages"], 0, 20),
            "directory_mode": form.get("directory_mode") == "on",
            "profiles_per_page": num("profiles_per_page", d["profiles_per_page"], 0, 60),
            "site_pages": num("site_pages", d["site_pages"], 0, 30),
            "cache_days": num("cache_days", d["cache_days"], 0, 30),
            "delay": num("delay", d["delay"], 0, 30, float),
            "robots": form.get("robots") == "on",
            "max_chunks": num("max_chunks", d["max_chunks"], 1, 8),
        }
        set_setting(s, "crawler", cfg)
        s.commit()
        if form.get("clear_cache"):
            n = crawl.purge_cache(0)
            flash(request, f"Crawler settings saved. {n} cached pages cleared.")
        else:
            flash(request, "Crawler settings saved.")
    return go("/settings/crawler")


# ---------- settings: connections (API keys used by search methods) ----------

EBAY_SITES = [("EBAY_GB", "ebay.co.uk", "UK"), ("EBAY_DE", "ebay.de", "Germany"), ("EBAY_IT", "ebay.it", "Italy"),
              ("EBAY_FR", "ebay.fr", "France"), ("EBAY_US", "ebay.com", "USA"), ("EBAY_CA", "ebay.ca", "Canada"),
              ("EBAY_ES", "ebay.es", "Spain"), ("EBAY_AU", "ebay.com.au", "Australia"),
              ("EBAY_NL", "ebay.nl", "Netherlands"), ("EBAY_AT", "ebay.at", "Austria")]
CONNECTION_DEFAULTS = {
    "ebay": {"client_id": "", "client_secret": "", "sites": ["EBAY_GB", "EBAY_DE", "EBAY_IT", "EBAY_FR",
                                                              "EBAY_US", "EBAY_CA"], "business_only": True},
    "etsy": {"api_key": "", "shared_secret": ""},
}


def connections(s) -> dict:
    saved = get_setting(s, "connections", {}) or {}
    return {k: {**v, **(saved.get(k) or {})} for k, v in CONNECTION_DEFAULTS.items()}


@app.get("/settings/connections", response_class=HTMLResponse)
def connections_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        return render(request, s, user, "connections.html", all=all_groups(s), active_nav="connections",
                      conn=connections(s), ebay_sites=EBAY_SITES)


@app.post("/settings/connections")
async def connections_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_groups")
        conn = connections(s)

        def keep(new: str, old: str) -> str:   # empty password box = keep the saved value
            new = str(new or "").strip()
            return old if not new else ("" if new == "-" else new)
        conn["ebay"].update({
            "client_id": keep(form.get("ebay_client_id"), conn["ebay"]["client_id"]),
            "client_secret": keep(form.get("ebay_client_secret"), conn["ebay"]["client_secret"]),
            "sites": [x for x in form.getlist("ebay_sites") if x in {c for c, _, _ in EBAY_SITES}],
            "business_only": form.get("ebay_business_only") == "on",
        })
        conn["etsy"].update({
            "api_key": keep(form.get("etsy_api_key"), conn["etsy"]["api_key"]),
            "shared_secret": keep(form.get("etsy_shared_secret"), conn["etsy"]["shared_secret"]),
        })
        set_setting(s, "connections", conn)
        s.commit()
        flash(request, "Connections saved. They will be used by the eBay and Etsy search methods.")
    return go("/settings/connections")


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
        back_url = f"/settings/users/{uid}" if uid else "/settings/users"
        target = s.get(User, uid) if uid else None
        if uid and not target:
            return go("/settings/users")
        if len(username) < 3:
            flash(request, "Username needs at least 3 characters.", True)
            return go(back_url)
        if s.scalar(select(User).where(User.username == username, User.id != (uid or 0))):
            flash(request, "That username is already taken.", True)
            return go(back_url)
        if (not target or password) and len(password) < 8:
            flash(request, "Password needs at least 8 characters.", True)
            return go(back_url)
        if role == "Admin" and not me.is_admin:
            flash(request, "Only an admin can make someone an admin.", True)
            return go(back_url)
        if target and target.is_admin and (role != "Admin" or not active):
            others = s.scalar(select(func.count(User.id)).where(User.is_admin, User.active, User.id != target.id))
            if not others:
                flash(request, "This is the last active admin, so it must stay an active admin.", True)
                return go(back_url)

        target = target or User(password_hash="", prefs={})
        target.username, target.role, target.active = username, role, (active if uid else True)
        target.is_admin = role == "Admin"
        target.perms = ",".join(PERM_KEYS if target.is_admin else perms)
        target.all_groups = target.is_admin or all_grp
        target.group_links = [] if target.all_groups else [UserGroup(group_id=g) for g in sorted(group_ids)]
        if password:
            target.password_hash = hash_password(password)
        s.add(target)
        s.commit()
        flash(request, f"User “{username}” saved.")
        return go(f"/settings/users/{target.id}")


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}
