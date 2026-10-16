"""First run, log in, log out."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from ..auth import ADMIN, hash_password, verify_password
from ..db import Role, SessionLocal, User
from .common import go, remember_password, templates
from .people_routes import record_login

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    with SessionLocal() as s:
        if s.scalar(select(func.count(User.id))):
            return go("/login")
    return templates.TemplateResponse(request, "setup.html", {"error": None})


@router.post("/setup")
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
        admin = s.scalar(select(Role).where(Role.name == ADMIN))
        user = User(username=username, password_hash=hash_password(password), is_admin=True, role=ADMIN,
                    role_id=admin.id if admin else None, perms="view,request,keywords,edit,delete,manage_groups,manage_users",
                    all_groups=True, active=True, prefs={})
        s.add(user)
        s.commit()
        request.session["uid"] = user.id
        remember_password(request, user)
    return go("/")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    with SessionLocal() as s:
        if not s.scalar(select(func.count(User.id))):
            return go("/setup")
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with SessionLocal() as s:
        name = username.strip().lower()
        user = s.scalar(select(User).where(User.username == name))
        ok = bool(user and verify_password(password, user.password_hash))
        if not ok or not user.active:
            record_login(s, request, user, name, False, "disabled" if ok else "wrong password")
            s.commit()
            return templates.TemplateResponse(request, "login.html",
                                              {"error": "Wrong username or password." if not ok else
                                               "This account is switched off. Ask an admin.", "username": username},
                                              status_code=401)
        record_login(s, request, user, name, True)
        s.commit()
        request.session.clear()
        request.session["uid"] = user.id
        remember_password(request, user)
        if user.must_change:
            return go("/account/password")
    return go("/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/login")
