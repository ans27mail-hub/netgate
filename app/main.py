"""NetGate web app. The pages live in app/web/*_routes.py; shared helpers in app/web/common.py."""
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from .db import SessionLocal, User, init_db, log
from .web import (add_routes, auth_routes, contacts_routes, help_routes, inbox_routes, people_routes,
                  requests_routes, settings_routes)
from .web.common import BASE, SECRET, VERSION, Forbidden, LoginRequired

app = FastAPI(title="NetGate")
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax", max_age=14 * 24 * 3600)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
for module in (auth_routes, inbox_routes, add_routes, contacts_routes, requests_routes, settings_routes,
               people_routes, help_routes):
    app.include_router(module.router)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc):
    with SessionLocal() as s:
        has_users = s.scalar(select(func.count(User.id)))
    return RedirectResponse("/login" if has_users else "/setup", status_code=303)


@app.exception_handler(Forbidden)
async def _forbidden(request: Request, exc):
    return HTMLResponse("<p style='font-family:sans-serif;padding:40px'>You don't have permission for this. "
                        "<a href='/'>Back to NetGate</a></p>", status_code=403)


@app.exception_handler(Exception)
async def _error(request: Request, exc):
    log("error", "web", f"{request.method} {request.url.path}: {type(exc).__name__}: {exc}", traceback.format_exc())
    return HTMLResponse("<p style='font-family:sans-serif;padding:40px'>Something went wrong on this page. "
                        "It has been written to the log (Developer tools → Logs). <a href='/'>Back to NetGate</a></p>",
                        status_code=500)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}
