"""Users and roles."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from ..auth import ADMIN, OLD_PERMS, PERM_KEYS, join
from ..db import Role, SessionLocal, User, UserGroup
from .common import all_groups, current_user, flash, go, render, require

router = APIRouter()


def roles_of(s):
    return s.scalars(select(Role).order_by(Role.position, Role.id)).all()


# ---------- users ----------

@router.get("/settings/users", response_class=HTMLResponse)
def users_page(request: Request):
    return _user_page(request, None)


@router.get("/settings/users/{uid}", response_class=HTMLResponse)
def user_page(request: Request, uid: int):
    return _user_page(request, uid)


def _user_page(request: Request, uid: int | None):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_users")
        users = s.scalars(select(User).order_by(User.is_admin.desc(), User.username)).all()
        edit = s.get(User, uid) if uid else None
        roles = roles_of(s)
        group_names = {g.id: g.name for g in all_groups(s)}
        return render(request, s, user, "users.html", users=users, edit=edit, all=all_groups(s), roles=roles,
                      role_perms={r.id: sorted(r.perm_set) for r in roles},
                      role_dirs={r.id: {"all": r.all_groups, "ids": r.group_ids or []} for r in roles},
                      group_names=group_names, active_nav="users", help="users-roles")


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
    all_grp = form.get("access") != "some"
    group_ids = {int(g) for g in form.getlist("groups") if str(g).isdigit()}
    active = form.get("active") == "on"

    with SessionLocal() as s:
        me = current_user(s, request)
        require(me, "manage_users")
        back_url = f"/settings/users/{uid}" if uid else "/settings/users"
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
        if (not target or password) and len(password) < 8:
            flash(request, "Password needs at least 8 characters.", True)
            return go(back_url)
        if role.locked and not me.is_admin:
            flash(request, "Only an admin can make someone an admin.", True)
            return go(back_url)
        if target and target.is_admin and (not role.locked or not active):
            others = s.scalar(select(func.count(User.id)).where(User.is_admin, User.active, User.id != target.id))
            if not others:
                flash(request, "This is the last active admin, so it must stay an active admin.", True)
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
        if not uid and form.get("access") is None:   # new user without a choice: the role's default
            all_grp, group_ids = role.all_groups, set(role.group_ids or [])
        target.all_groups = target.is_admin or all_grp
        target.group_links = [] if target.all_groups else [UserGroup(group_id=g) for g in sorted(group_ids)]
        if password:
            from ..auth import hash_password
            target.password_hash = hash_password(password)
        s.add(target)
        s.commit()
        flash(request, f"User “{username}” saved.")
        return go(f"/settings/users/{target.id}")


# ---------- roles ----------

@router.get("/settings/roles", response_class=HTMLResponse)
def roles_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        roles = roles_of(s)
        used = dict(s.execute(select(User.role_id, func.count(User.id)).group_by(User.role_id)).all())
        return render(request, s, user, "roles.html", roles=roles, used=used, all=all_groups(s),
                      active_nav="roles", help="users-roles")


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
        if not name or s.scalar(select(Role).where(Role.name == name)):
            flash(request, "Give the role a new, unique name.", True)
            return go("/settings/roles")
        src = s.get(Role, copy) if copy else None
        pos = (s.scalar(select(func.max(Role.position))) or 0) + 1
        s.add(Role(name=name, description="", perms=join(src.perm_set) if src else "view", position=pos))
        s.commit()
        flash(request, f"Role “{name}” created" + (f" from {src.name}" if src else "") + ". Tick its permissions below.")
    return go("/settings/roles")


@router.post("/settings/roles/{rid}/delete")
def role_delete(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_roles")
        r = s.get(Role, rid)
        n = s.scalar(select(func.count(User.id)).where(User.role_id == rid))
        if not r or r.locked or r.name == ADMIN:
            return go("/settings/roles")
        if n:
            flash(request, f"{n} user(s) still have the role {r.name}. Give them another role first.", True)
            return go("/settings/roles")
        s.delete(r)
        s.commit()
        flash(request, f"Role “{r.name}” deleted.")
    return go("/settings/roles")


def legacy_perms(effective: set) -> str:
    """v0.4 permission names for the same access."""
    return ",".join(old for old, new in OLD_PERMS.items() if new[0] in effective)
