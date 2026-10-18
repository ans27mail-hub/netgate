"""Settings → Search Engines (v0.8): turn SearXNG's engines on / off, see which work or block, Test Now."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from .. import crawl
from .. import engines as EN
from ..db import SearchLog, SessionLocal
from .common import current_user, flash, go, render, require
from .settings_routes import _settings_ctx

router = APIRouter()
TEST_QUERY = "leather gloves manufacturer"


def _page(request, s, user, tested=None, test_query=""):
    cfg = EN.searx_engines()
    names = EN.catalogue(cfg)
    choice = EN.saved(s)
    on = set(choice.get("on") or []) if choice.get("set") else set(EN.default_on(cfg))
    names += [n for n in sorted(on) if n not in names]
    status = EN.status(s, names)
    recent = s.scalars(select(SearchLog).order_by(SearchLog.id.desc()).limit(12)).all()
    week = datetime.utcnow() - timedelta(days=EN.RECENT_DAYS)
    total7 = s.scalar(select(func.count(SearchLog.id)).where(SearchLog.at >= week)) or 0
    default = set(EN.default_on(cfg))
    rows = [{"name": n, "label": EN.label(n), "note": EN.NOTES.get(n, ""), "on": n in on, "default": n in default,
             **status[n]} for n in names]
    return render(request, s, user, "engines.html", active_nav="engines", help="search-engines", rows=rows,
                  custom=bool(choice.get("set")), reachable=cfg is not None, recent=recent, total7=total7,
                  tested=tested, test_query=test_query or TEST_QUERY, label=EN.label, **_settings_ctx(s))


@router.get("/settings/search-engines", response_class=HTMLResponse)
def engines_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        return _page(request, s, user)


@router.post("/settings/search-engines")
async def engines_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        if form.get("action") == "reset":
            EN.save_choice(s, None)
            s.commit()
            flash(request, "Back to SearXNG's own choice of engines.")
            return go("/settings/search-engines")
        allowed = set(EN.catalogue(EN.searx_engines())) | set(EN.saved(s).get("on") or [])
        on = [n for n in form.getlist("on") if n in allowed]
        if not on:
            flash(request, "Keep at least one search engine switched on — otherwise no search can run.", True)
            return go("/settings/search-engines")
        EN.save_choice(s, on)
        s.commit()
        flash(request, "Saved. Searches now use: " + ", ".join(EN.label(n) for n in on) + ".")
    return go("/settings/search-engines")


def _test_one(query: str, name: str) -> tuple[str, int, str]:
    res = crawl.search(query, engines=[name], test=True)
    errors = dict(getattr(crawl.last_search, "errors", {}) or {})
    return name, len(res), errors.get(name) or errors.get("searxng") or ""


@router.post("/settings/search-engines/test", response_class=HTMLResponse)
async def engines_test(request: Request):
    """Ask each engine that is switched on, one at a time (in parallel), with the same test search."""
    form = await request.form()
    query = str(form.get("query") or "").strip()[:200] or TEST_QUERY
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        choice = EN.saved(s)
        on = list(choice.get("on") or []) if choice.get("set") else EN.default_on(EN.searx_engines())
    crawl.set_search_job(None)
    with ThreadPoolExecutor(max_workers=6) as pool:
        tested = {n: (count, err) for n, count, err in pool.map(lambda n: _test_one(query, n), on)}
    with SessionLocal() as s:
        user = current_user(s, request)
        return _page(request, s, user, tested=tested, test_query=query)
