"""People: users, roles, login history, and each person's own password page."""
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from ..auth import ADMIN, OLD_PERMS, PERM_KEYS, can, hash_password, join, verify_password
from ..db import Job, Login, Role, SessionLocal, User, UserGroup
from .common import all_groups, current_user, flash, go, remember_password, render, require, require_any

router = APIRouter()


def roles_of(s):
    return s.scalars(select(Role).order_by(Role.position, Role.id)).all()


def _other_active_admins(s, uid) -> int:
    return s.scalar(select(func.count(User.id)).where(User.is_admin, User.active, User.id != uid)) or 0


# ---------- users list ----------

@router.get("/people")
def people(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require_any(user, ["manage_users", "manage_roles"])
        return go("/settings/users" if can(user, "manage_users") else "/settings/roles")


@router.get("/settings/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", role: int = 0, status: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_users")
        stmt = select(User).order_by(User.is_admin.desc(), User.username)
        if q.strip():
            stmt = stmt.where(User.username.ilike(f"%{q.strip()}%"))
        if role:
            stmt = stmt.where(User.role_id == role)
        if status == "active":
            stmt = stmt.where(User.active)
        elif status == "disabled":
            stmt = stmt.where(User.active.is_(False))
        users = s.scalars(stmt).all()
        total = s.scalar(select(func.count(User.id)))
        return render(request, s, user, "users.html", users=users, total=total, roles=roles_of(s), f_q=q,
                      f_role=role, f_status=status, group_names={g.id: g.name for g in all_groups(s)},
                      active_nav="users", help="people")


# ---------- one user ----------

@router.get("/settings/users/new", response_class=HTMLResponse)
def user_new_page(request: Request):
    return _user_page(request, None)


@router.get("/settings/users/{uid}", response_class=HTMLResponse)
def user_page(request: Request, uid: int):
    return _user_page(request, uid)


def _user_page(request: Request, uid: int | None):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_users")
        edit = s.get(User, uid) if uid else None
        if uid and not edit:
            return go("/settings/users")
        roles = roles_of(s)
        logins = s.scalars(select(Login).where(Login.user_id == uid).order_by(Login.id.desc()).limit(8)).all() \
            if edit else []
        jobs_n = s.scalar(select(func.count(Job.id)).where(Job.user_id == uid)) if edit else 0
        from .contacts_routes import _all_fields
        return render(request, s, user, "user_edit.html", edit=edit, all=all_groups(s), roles=roles,
                      field_choices=[f for f in _all_fields(s) if f.key not in ("city", "country")],
                      role_perms={r.id: sorted(r.perm_set) for r in roles},
                      role_dirs={r.id: {"all": r.all_groups, "ids": r.group_ids or [], "cs": r.contacts_scope or "all"}
                                 for r in roles},
                      logins=logins, jobs_n=jobs_n, active_nav="users", help="people")


@router.post("/settings/users/new")
async def user_create(request: Request):
    return await _user_save(request, None)


@router.post("/settings/users/{uid}")
async def user_update(request: Request, uid: int):
    return await _user_save(request, uid)


async def _user_save(request: Request, uid: int | None):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    role_id = int(form.get("role_id") or 0)
    perms = {p for p in form.getlist("perms") if p in PERM_KEYS}
    customise = form.get("customise") == "on"
    access = form.get("access") if form.get("access") in ("all", "some", "own") else None
    all_grp = (access or "all") == "all"
    group_ids = {int(g) for g in form.getlist("groups") if str(g).isdigit()}
    contacts_scope = "own" if form.get("contacts_scope") == "own" else "all"
    existing_view = "fields" if form.get("existing_view") == "fields" else "full"
    existing_fields = [k for k in form.getlist("existing_fields") if k][:40]
    active = form.get("active") == "on"

    with SessionLocal() as s:
        me = current_user(s, request)
        require(me, "manage_users")
        back_url = f"/settings/users/{uid}" if uid else "/settings/users/new"
        target = s.get(User, uid) if uid else None
        role = s.get(Role, role_id)
        if uid and not target:
            return go("/settings/users")
        if not role:
            flash(request, "Choose a role.", True)
            return go(back_url)
        if len(username) < 3:
            flash(request, "Username needs at least 3 characters.", True)
            return go(back_url)
        if s.scalar(select(User).where(User.username == username, User.id != (uid or 0))):
            flash(request, "That username is already taken.", True)
            return go(back_url)
        if not target and len(password) < 8:
            flash(request, "Password needs at least 8 characters.", True)
            return go(back_url)
        if role.locked and not me.is_admin:
            flash(request, "Only an admin can make someone an admin.", True)
            return go(back_url)
        if target and target.is_admin and (not role.locked or not active) and not _other_active_admins(s, target.id):
            flash(request, "This is the last active admin, so it must stay an active admin.", True)
            return go(back_url)
        if target and target.id == me.id and not active:
            flash(request, "You can't disable your own account.", True)
            return go(back_url)

        target = target or User(password_hash="", prefs={})
        target.username, target.active = username, (active if uid else True)
        target.role_id, target.role, target.is_admin = role.id, role.name, bool(role.locked)
        target.role_obj = role
        rp = role.perm_set
        if customise and not role.locked:
            target.extra_perms, target.removed_perms = join(perms - rp), join(rp - perms)
        else:
            target.extra_perms, target.removed_perms = "", ""
        target.perms = legacy_perms(target.perm_set)   # so a rollback to v0.4 keeps working
        if not uid and access is None:   # new user without a choice: the role's default
            all_grp, group_ids = role.all_groups, set(role.group_ids or [])
            access = "all" if all_grp else "some"
        if not uid and form.get("contacts_scope") is None:
            contacts_scope, existing_view = role.contacts_scope or "all", role.existing_view or "full"
            existing_fields = list(role.existing_fields or [])
        target.all_groups = target.is_admin or all_grp
        target.dir_scope = "all" if target.all_groups else (access or "some")
        keep = [] if target.all_groups or target.dir_scope == "own" else sorted(group_ids)
        target.group_links = [UserGroup(group_id=g) for g in keep]
        target.contacts_scope = "all" if target.is_admin else contacts_scope
        target.existing_view, target.existing_fields = existing_view, existing_fields
        if not uid:
            target.password_hash = hash_password(password)
            target.must_change = form.get("must_change") == "on"
        s.add(target)
        s.commit()
        flash(request, f"User “{username}” saved.")
        return go(f"/settings/users/{target.id}")


@router.post("/settings/users/{uid}/password")
async def user_password(request: Request, uid: int):
    """An admin sets a new (temporary) password for someone."""
    form = await request.form()
    password = str(form.get("password") or "")
    with SessionLocal() as s:
        me = current_user(s, request)
        require(me, "manage_users")
        target = s.get(User, uid)
        if not target:
            return go("/settings/users")
        if target.is_admin and not me.is_admin:
            flash(request, "Only an admin can reset an admin's password.", True)
            return go(f"/settings/users/{uid}")
        if len(password) < 8:
            flash(request, "The new password needs at least 8 characters.", True)
            return go(f"/settings/users/{uid}")
        target.password_hash = hash_password(password)
        target.must_change = form.get("must_change") == "on" and target.id != me.id
        s.commit()
        flash(request, f"New password set for {target.username}."
                       + (" They must choose their own when they next log in." if target.must_change else "")
                       + (" They are logged out everywhere." if target.id != me.id else ""))
    return go(f"/settings/users/{uid}")


@router.post("/settings/users/{uid}/delete")
async def user_delete(request: Request, uid: int):
    form = await request.form()
    with SessionLocal() as s:
        me = current_user(s, request)
        require(me, "manage_users")
        target = s.get(User, uid)
        if not target:
            return go("/settings/users")
        if target.id == me.id:
            flash(request, "You can't delete your own account.", True)
            return go(f"/settings/users/{uid}")
        if target.is_admin and not me.is_admin:
            flash(request, "Only an admin can delete an admin.", True)
            return go(f"/settings/users/{uid}")
        if target.is_admin and not _other_active_admins(s, target.id):
            flash(request, "This is the last active admin, so it can't be deleted.", True)
            return go(f"/settings/users/{uid}")
        if str(form.get("confirm") or "").strip().lower() != target.username:
            flash(request, f"Type the username “{target.username}” to confirm.", True)
            return go(f"/settings/users/{uid}")
        name = target.username
        s.delete(target)   # contacts, decisions and history keep their data; requests keep running without an owner
        s.commit()
        flash(request, f"User “{name}” deleted. Everything they found, added or decided is kept, "
                       "marked “(deleted user)”.")
    return go("/settings/users")


# ---------- login history ----------

@router.get("/settings/logins", response_class=HTMLResponse)
def logins_page(request: Request, user_id: int = 0, failed: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_users")
        stmt = select(Login).order_by(Login.id.desc()).limit(300)
        if user_id:
            stmt = stmt.where(Login.user_id == user_id)
        if failed:
            stmt = stmt.where(Login.ok.is_(False))
        users = s.scalars(select(User).order_by(User.username)).all()
        return render(request, s, user, "logins.html", rows=s.scalars(stmt).all(), users=users,
                      f_user=user_id, f_failed=failed, active_nav="logins", help="people")


def record_login(s, request: Request, user, username: str, ok: bool, note: str = ""):
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or \
        (request.client.host if request.client else "")
    s.add(Login(user_id=user.id if user else None, username=username[:80], ok=ok, ip=ip[:64],
                agent=short_agent(request.headers.get("user-agent") or ""), note=note))
    if ok and user:
        user.last_login_at = datetime.utcnow()


def short_agent(ua: str) -> str:
    """'Chrome on Windows' from a long browser string."""
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                            ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "")
    system = next((name for key, name in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"),
                                           ("iPad", "iPad"), ("Mac OS", "Mac"), ("Linux", "Linux")) if key in ua), "")
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or ua[:60]


# ---------- my password ----------

@router.get("/account/password", response_class=HTMLResponse)
def my_password_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request, allow_must_change=True)
        return render(request, s, user, "my_password.html", active_nav="account", help="people",
                      all=all_groups(s))


@router.post("/account/password")
async def my_password(request: Request):
    form = await request.form()
    old, new, new2 = (str(form.get(k) or "") for k in ("old", "new", "new2"))
    with SessionLocal() as s:
        user = current_user(s, request, allow_must_change=True)
        if not verify_password(old, user.password_hash):
            flash(request, "Your current password is not right.", True)
        elif len(new) < 8:
            flash(request, "The new password needs at least 8 characters.", True)
        elif new != new2:
            flash(request, "The two new passwords don't match.", True)
        elif new == old:
            flash(request, "Choose a password different from the old one.", True)
        else:
            user.password_hash, user.must_change = hash_password(new), False
            s.commit()
            remember_password(request, user)
            flash(request, "Password changed.")
            return go("/")
    return go("/account/password")


# ---------- roles ----------

@router.get("/settings/roles", response_class=HTMLResponse)
def roles_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        roles = roles_of(s)
        used = dict(s.execute(select(User.role_id, func.count(User.id)).group_by(User.role_id)).all())
        return render(request, s, user, "roles.html", roles=roles, used=used, all=all_groups(s),
                      active_nav="roles", help="people")


@router.post("/settings/roles")
async def roles_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        for r in roles_of(s):
            if r.locked:
                continue
            name = str(form.get(f"name_{r.id}") or r.name).strip()[:60]
            if name and name != r.name and not s.scalar(select(Role).where(Role.name == name, Role.id != r.id)):
                r.name = name
                for u in s.scalars(select(User).where(User.role_id == r.id)).all():
                    u.role = name
            r.description = str(form.get(f"desc_{r.id}") or "").strip()[:300]
            r.perms = join({p for p in PERM_KEYS if form.get(f"p_{r.id}_{p}") == "on"})
            r.all_groups = form.get(f"dirs_{r.id}") != "some"
            r.group_ids = [int(g) for g in form.getlist(f"g_{r.id}") if str(g).isdigit()]
            r.contacts_scope = "own" if form.get(f"cs_{r.id}") == "own" else "all"
            r.existing_view = "fields" if form.get(f"ev_{r.id}") == "fields" else "full"
        for u in s.scalars(select(User)).all():   # keep the rollback copy of permissions in step
            u.perms = legacy_perms(u.perm_set)
        s.commit()
        flash(request, "Roles saved. Everyone with a role now has its new permissions.")
    return go("/settings/roles")


@router.post("/settings/roles/new")
async def role_new(request: Request):
    form = await request.form()
    name = str(form.get("name") or "").strip()[:60]
    copy = int(form.get("copy") or 0)
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        if not name or s.scalar(select(Role).where(func.lower(Role.name) == name.lower())):
            flash(request, "Give the role a new, unique name.", True)
            return go("/settings/roles")
        src = s.get(Role, copy) if copy else None
        pos = (s.scalar(select(func.max(Role.position))) or 0) + 1
        perms = join(src.perm_set) if src else "view"
        s.add(Role(name=name, description=(f"Copy of {src.name}. " + (src.description or "")).strip()[:300] if src else "",
                   perms=perms, all_groups=src.all_groups if src else True,
                   group_ids=list(src.group_ids or []) if src else [], position=pos,
                   contacts_scope=src.contacts_scope if src else "all",
                   existing_view=src.existing_view if src else "full",
                   existing_fields=list(src.existing_fields or []) if src else []))
        s.commit()
        flash(request, f"Role “{name}” created" + (f" as a copy of {src.name}" if src else "")
              + ". Tick its permissions below and press Save roles.")
    return go("/settings/roles")


@router.post("/settings/roles/{rid}/delete")
async def role_delete(request: Request, rid: int):
    form = await request.form()
    move_to = int(form.get("move_to") or 0)
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        r = s.get(Role, rid)
        if not r or r.locked or r.name == ADMIN:
            flash(request, "The Admin role can't be deleted.", True)
            return go("/settings/roles")
        users = s.scalars(select(User).where(User.role_id == rid)).all()
        if users:
            dest = s.get(Role, move_to) if move_to != rid else None
            if not dest:
                flash(request, f"{len(users)} user(s) have the role {r.name}. Choose which role they get instead.", True)
                return go("/settings/roles")
            if dest.locked and not user.is_admin:
                flash(request, "Only an admin can give people the Admin role.", True)
                return go("/settings/roles")
            for u in users:
                u.role_id, u.role, u.is_admin, u.role_obj = dest.id, dest.name, bool(dest.locked), dest
                if dest.locked:
                    u.all_groups, u.extra_perms, u.removed_perms = True, "", ""
                u.perms = legacy_perms(u.perm_set)
        name = r.name
        s.delete(r)
        s.commit()
        flash(request, f"Role “{name}” deleted."
              + (f" {len(users)} user(s) now have the role {dest.name}." if users else ""))
    return go("/settings/roles")


def legacy_perms(effective: set) -> str:
    """v0.4 permission names for the same access."""
    return ",".join(old for old, new in OLD_PERMS.items() if new[0] in effective)

