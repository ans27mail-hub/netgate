"""Browser search (v1.0): its settings (in Settings → Search Engines) and “Solve CAPTCHA Yourself”."""
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select

from .. import browser as BR
from ..auth import can
from ..db import CaptchaWait, Job, SessionLocal
from .common import Forbidden, can_control, current_user, flash, go, render, require, templates

router = APIRouter()


@router.post("/settings/browser")
async def browser_settings_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        if form.get("resume") in BR.ENGINES:
            BR.resume_engine(s, form.get("resume"))
            s.commit()
            flash(request, f"{BR.label(form.get('resume'))} can be used by Browser search again.")
            return go("/settings/search-engines#browser")

        def num(key, default, lo, hi):
            try:
                return max(lo, min(hi, float(form.get(key))))
            except (TypeError, ValueError):
                return default
        cfg = BR.settings(s)
        engines = [e for e in form.getlist("engines") if e in BR.ENGINES]
        if not engines:
            flash(request, "Keep at least one search engine on for Browser search.", True)
            return go("/settings/search-engines#browser")
        cfg.update({"engines": engines, "pause": int(num("pause", 20, 5, 600)), "per_hour": int(num("per_hour", 20, 1, 200)),
                    "captcha_hours": num("captcha_hours", 6, 0.5, 72), "wait_minutes": int(num("wait_minutes", 5, 1, 15))})
        BR.save_settings(s, cfg)
        s.commit()
        flash(request, "Browser search settings saved.")
    return go("/settings/search-engines#browser")


# ---------- Solve CAPTCHA Yourself ----------

def _wait_for(s, user, wid: int):
    w = s.get(CaptchaWait, wid)
    if not w:
        return None, None
    job = s.get(Job, w.job_id) if w.job_id else None
    if not (job and can_control(user, job)) and not can(user, "requests_all"):
        raise Forbidden
    return w, job


def waiting_for(s, user) -> list:
    """CAPTCHAs this person may solve (their own requests, or everyone's with *Control everyone's requests*)."""
    rows = s.scalars(select(CaptchaWait).where(CaptchaWait.status == "waiting").order_by(CaptchaWait.id)).all()
    out = []
    for w in rows:
        job = s.get(Job, w.job_id) if w.job_id else None
        if can(user, "requests_all") or (job and can_control(user, job)):
            out.append(w)
    return out


@router.get("/captcha/mine")
def captcha_mine(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        rows = waiting_for(s, user) if can(user, "see_requests") else []
        # the pop-up opens by itself only for the person who started the request
        own = [w for w in rows if w.user_id == user.id]
        return JSONResponse({"waiting": len(rows), "popup": own[0].id if own else None,
                             "engine": BR.label(own[0].engine) if own else ""})


@router.get("/captcha/{wid}", response_class=HTMLResponse)
def captcha_page(request: Request, wid: int, frame: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        w, job = _wait_for(s, user, wid)
        if not w:
            return go("/requests")
        ctx = {"w": w, "job": job, "engine": BR.label(w.engine), "frame": frame}
        if frame:
            return templates.TemplateResponse(request, "_captcha.html", {"user": user, **ctx})
        return render(request, s, user, "captcha.html", active_nav="requests", help="browser-search", **ctx)


@router.get("/captcha/{wid}/shot")
def captcha_shot(request: Request, wid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        w, _ = _wait_for(s, user, wid)
        if not w or w.status != "waiting":
            return Response(status_code=404)
        sid = w.sid
    png = BR.shot(sid)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"}) if png \
        else Response(status_code=404)


@router.post("/captcha/{wid}/{what}")
async def captcha_act(request: Request, wid: int, what: str):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        w, _ = _wait_for(s, user, wid)
        if not w or w.status != "waiting":
            return JSONResponse({"status": w.status if w else "gone"})
        if what == "giveup":
            w.status, w.ended_at = "gave_up", datetime.utcnow()
            s.commit()
            return JSONResponse({"status": "gave_up"})
        sid = w.sid
    if what == "click":
        try:
            x, y = float(form.get("x") or 0), float(form.get("y") or 0)
        except ValueError:
            x = y = 0
        BR.act(sid, "click", x=x, y=y)
    elif what == "type":
        BR.act(sid, "type", text=str(form.get("text") or "")[:200])
    elif what == "key":
        BR.act(sid, "key", key=str(form.get("key") or ""))
    page = BR.state(sid)
    solved = bool(page.get("html")) and not BR.is_captcha(page)
    if solved:
        with SessionLocal() as s:
            w = s.get(CaptchaWait, wid)
            if w and w.status == "waiting":
                w.status, w.solved_by, w.ended_at = "solved", user.id, datetime.utcnow()
                s.commit()
    return JSONResponse({"status": "solved" if solved else "waiting"})
