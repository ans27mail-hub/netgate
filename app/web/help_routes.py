"""Help Center and developer tools."""
import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from .. import help as H
from .. import learn
from ..auth import can
from ..db import AppLog, Decision, SessionLocal, get_setting, set_setting
from .common import Forbidden, all_groups, current_user, flash, go, render, require, templates

router = APIRouter()


@router.get("/help", response_class=HTMLResponse)
def help_home(request: Request, q: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        pages = H.for_user(user)
        found = H.search(q, user, 8) if q.strip() else []
        sections = []
        for name in H.SECTIONS + sorted({p["section"] for p in pages} - set(H.SECTIONS)):
            items = [p for p in pages if p["section"] == name]
            if items:
                sections.append((name, items))
        return render(request, s, user, "help.html", active_nav="help", sections=sections, page=None,
                      found=found, q=q, help="")


@router.get("/help/whats-new", response_class=HTMLResponse)
def whats_new(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        page = {"slug": "whats-new", "title": "What's new", "section": "Start here", "html": H.changelog_html()}
        return render(request, s, user, "help.html", active_nav="help", sections=[], page=page, found=[], q="",
                      help="", siblings=H.for_user(user))


@router.get("/help/{slug}", response_class=HTMLResponse)
def help_page(request: Request, slug: str, partial: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        page = H.get(slug, user)
        if partial:
            return templates.TemplateResponse(request, "_help_panel.html", {"page": page, "slug": slug})
        if not page:
            return go("/help")
        return render(request, s, user, "help.html", active_nav="help", sections=[], page=page, found=[], q="",
                      help="", siblings=[p for p in H.for_user(user) if p["section"] == page["section"]])


@router.post("/help/ask", response_class=HTMLResponse)
def help_ask(request: Request, question: str = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
    result = H.ask(question.strip()[:500], user)
    return templates.TemplateResponse(request, "_help_answer.html", {"r": result, "question": question})


# ---------- developer tools ----------

@router.get("/dev", response_class=HTMLResponse)
def dev_home(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        if not any(can(user, p) for p in ("debug", "logs", "tester", "training_export", "dev_help")):
            raise Forbidden
        n_dec = s.scalar(select(func.count(Decision.id)))
        n_err = s.scalar(select(func.count(AppLog.id)).where(AppLog.level == "error"))
        return render(request, s, user, "dev.html", active_nav="dev", help="developer", n_dec=n_dec, n_err=n_err,
                      dev=get_setting(s, "dev", {}) or {}, groups=all_groups(s))


@router.post("/dev/settings")
def dev_settings(request: Request, trace: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "debug")
        set_setting(s, "dev", {"trace": trace == "on"})
        s.commit()
        flash(request, "Debug traces " + ("on: new requests record what they read and ask." if trace == "on" else "off."))
    return go("/dev")


@router.get("/dev/logs", response_class=HTMLResponse)
def dev_logs(request: Request, level: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "logs")
        stmt = select(AppLog)
        if level:
            stmt = stmt.where(AppLog.level == level)
        rows = s.scalars(stmt.order_by(AppLog.id.desc()).limit(300)).all()
        return render(request, s, user, "dev_logs.html", active_nav="dev", help="developer", rows=rows, level=level)


@router.get("/dev/tester", response_class=HTMLResponse)
def dev_tester(request: Request, group: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "tester")
        return render(request, s, user, "dev_tester.html", active_nav="dev", help="developer", test=None,
                      groups=all_groups(s), sel_id=group)


@router.get("/dev/handbook", response_class=HTMLResponse)
@router.get("/dev/handbook/{slug}", response_class=HTMLResponse)
def handbook(request: Request, slug: str = "overview", q: str = ""):
    """The Developer Handbook: written pages (docs/dev) plus pages made from the code."""
    from .. import handbook as HB
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "dev_help")
        pages = HB.written()
        if slug in HB.AUTO:
            page = {"slug": slug, "title": HB.AUTO[slug], "kind": "auto", "updated": "made from the code just now",
                    "html": HB.html(HB.auto_page(slug, request.app))}
        else:
            page = next((p for p in pages if p["slug"] == slug), None)
            if page:
                page = {**page, "html": HB.html(page["body"])}
        results = HB.search(q) if q.strip() else []
        return render(request, s, user, "handbook.html", active_nav="dev", help="developer-tools", page=page,
                      guides=[p for p in pages if p["kind"] == "guide"],
                      features=[p for p in pages if p["kind"] == "feature"], auto=HB.AUTO, slug=slug, hq=q,
                      results=results, missing=HB.missing_features())


@router.post("/dev/handbook/ask", response_class=HTMLResponse)
def handbook_ask(request: Request, question: str = Form(...)):
    from .. import handbook as HB
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "dev_help")
    result = HB.ask(question.strip()[:500])
    return templates.TemplateResponse(request, "_handbook_answer.html", {"r": result, "question": question})


@router.get("/dev/training.jsonl")
def training_export(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "training_export")
        lines = [json.dumps(r, ensure_ascii=False) for r in learn.training_rows(s)]
    return Response("\n".join(lines) + "\n", media_type="application/jsonl",
                    headers={"Content-Disposition": 'attachment; filename="netgate-decisions.jsonl"'})
