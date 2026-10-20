"""Browser search (v1.0): NetGate's own Chromium (the renderer) opens Bing / DuckDuckGo (Google only if switched on)
like a person, reads the result pages and the pages they link to, and keeps going until the directory has enough
new companies (stop rule per directory: new companies, result pages, minutes).

Polite limits (Settings → Search Engines → Browser Search): a pause between searches on the same engine and a
maximum per hour. On a CAPTCHA the search waits: the person who started it gets a pop-up with a live picture of the
page and solves it themselves (“Solve CAPTCHA Yourself”); night jobs and other people's requests show a Solve
button on the Dashboard. NetGate never solves CAPTCHAs itself. Nobody solves it in time → that engine pauses for
some hours and the search goes on with the next engine.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from sqlalchemy import select

from . import engines as EN
from .db import CaptchaWait, SearchLog, SessionLocal, get_setting, log, set_setting

RENDER_URL = os.environ.get("RENDER_URL", "http://renderer:3000")
ENGINES = {
    "bing": ("Bing", "https://www.bing.com/search?q={q}&first={first}&setlang=en", 10),
    "duckduckgo": ("DuckDuckGo", "https://html.duckduckgo.com/html/?q={q}&s={first0}", 30),
    "google": ("Google", "https://www.google.com/search?q={q}&start={first0}&hl=en", 10),
}
try:   # tests point the engines at a local fake
    ENGINES.update({k: (ENGINES[k][0], v, ENGINES[k][2]) for k, v in
                    json.loads(os.environ.get("BROWSER_ENGINE_URLS") or "{}").items() if k in ENGINES})
except ValueError:
    pass
DEFAULTS = {"engines": ["bing", "duckduckgo"], "pause": 20, "per_hour": 20, "captcha_hours": 6, "wait_minutes": 5,
            "paused": {}}
CAPTCHA_WORDS = re.compile(r"captcha|unusual traffic|are you a robot|not a robot|verify you are human|"
                           r"bots use duckduckgo|anomaly-modal|b_captcha|cf-challenge|challenge-form|/sorry/", re.I)


def label(engine: str) -> str:
    return ENGINES.get(engine, (engine.title(),))[0]


def settings(s=None) -> dict:
    def read(ss):
        return {**DEFAULTS, **(get_setting(ss, "browser", {}) or {})}
    if s is not None:
        return read(s)
    with SessionLocal() as ss:
        return read(ss)


def save_settings(s, cfg: dict):
    set_setting(s, "browser", {k: cfg.get(k, v) for k, v in DEFAULTS.items()})


def paused_until(cfg: dict, engine: str) -> datetime | None:
    v = (cfg.get("paused") or {}).get(engine)
    try:
        until = datetime.fromisoformat(v) if v else None
    except ValueError:
        return None
    return until if until and until > datetime.utcnow() else None


def pause_engine(engine: str, hours: float, why: str = "CAPTCHA"):
    with SessionLocal() as s:
        cfg = settings(s)
        cfg["paused"] = {**(cfg.get("paused") or {}),
                         engine: (datetime.utcnow() + timedelta(hours=hours)).isoformat(timespec="seconds")}
        save_settings(s, cfg)
        s.commit()
    log("warning", "browser", f"Browser search: {label(engine)} paused for {hours:g} h ({why})")


def resume_engine(s, engine: str):
    cfg = settings(s)
    cfg["paused"] = {k: v for k, v in (cfg.get("paused") or {}).items() if k != engine}
    save_settings(s, cfg)


# ---------- the renderer's search sessions ----------

def _r(path: str, timeout: float = 60, **params):
    return httpx.post(f"{RENDER_URL}/session/{path}", params=params, timeout=timeout)


def open_page(sid: str, url: str) -> dict:
    r = _r("open", sid=sid, url=url, timeout=90)
    r.raise_for_status()
    return r.json()


def state(sid: str) -> dict:
    try:
        r = httpx.get(f"{RENDER_URL}/session/state", params={"sid": sid}, timeout=30)
        return r.json() if r.status_code == 200 else {"open": False}
    except (httpx.HTTPError, ValueError):
        return {"open": False}


def shot(sid: str) -> bytes:
    r = httpx.get(f"{RENDER_URL}/session/shot", params={"sid": sid}, timeout=30)
    return r.content if r.status_code == 200 else b""


def act(sid: str, what: str, **params) -> dict:
    try:
        r = _r(what, sid=sid, timeout=30, **params)
        return r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


def is_captcha(page: dict) -> bool:
    html = (page or {}).get("html") or ""
    url = (page or {}).get("url") or ""
    if "/sorry/" in url:
        return True
    head = html[:200_000]
    # a normal results page that only mentions the word deep in a result is not a CAPTCHA: look for the challenge
    return bool(CAPTCHA_WORDS.search(head)) and not _links_raw(head)


# ---------- reading result pages ----------

def _clean(u: str) -> str | None:
    if not u:
        return None
    if u.startswith("//"):
        u = "https:" + u
    p = urlparse(u)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        u = unquote((parse_qs(p.query).get("uddg") or [""])[0])
    elif "bing.com" in p.netloc and p.path.startswith("/ck/"):
        return None   # Bing's own redirect links: the real address is in the result's heading instead
    elif "google." in p.netloc and p.path == "/url":
        u = (parse_qs(p.query).get("q") or [""])[0]
    if not u.startswith(("http://", "https://")):
        return None
    host = urlparse(u).netloc
    if any(x in host for x in ("bing.com", "duckduckgo.com", "google.", "microsoft.com", "gstatic.com")):
        return None
    return u


def _links_raw(html: str) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for sel in ("li.b_algo h2 a", "a.result__a", "div.g a:has(h3)", "a[data-testid=result-title-a]", "h3 a"):
        for a in soup.select(sel):
            u = _clean(a.get("href") or "")
            if u and u not in out:
                out.append(u)
    return out


def result_links(html: str) -> list[str]:
    return _links_raw(html)[:30]


def engine_url(engine: str, query: str, pageno: int) -> str:
    _, tpl, step = ENGINES[engine]
    return tpl.format(q=quote_plus(query), first=(pageno - 1) * step + 1, first0=(pageno - 1) * step)


def searches_last_hour(engine: str) -> int:
    since = datetime.utcnow() - timedelta(hours=1)
    with SessionLocal() as s:
        rows = s.scalars(select(SearchLog.asked).where(SearchLog.at >= since)).all()
    return sum(1 for a in rows if a == [f"browser:{engine}"])


def last_search_at(engine: str) -> datetime | None:
    with SessionLocal() as s:
        for at, asked in s.execute(select(SearchLog.at, SearchLog.asked).order_by(SearchLog.id.desc()).limit(200)).all():
            if asked == [f"browser:{engine}"]:
                return at
    return None


# ---------- waiting for a person ----------

def wait_for_person(ctx, engine: str, sid: str, url: str, user_id: int | None) -> dict | None:
    """The request waits (up to the set minutes) while a person solves the CAPTCHA in the pop-up.
    Returns the page after it was solved, or None (engine paused)."""
    cfg = settings()
    with SessionLocal() as s:
        w = CaptchaWait(job_id=ctx.job_id, user_id=user_id, engine=engine, sid=sid, url=url, status="waiting")
        s.add(w)
        s.commit()
        wid = w.id
    ctx.trace("note", url, text=f"{label(engine)} asks for a CAPTCHA — waiting for a person to solve it "
                                f"(up to {cfg['wait_minutes']} minutes)", captcha=wid)
    deadline = time.time() + float(cfg["wait_minutes"]) * 60
    result = None
    try:
        while time.time() < deadline:
            ctx.step("searching", f"CAPTCHA on {label(engine)} — waiting for you to solve it (Solve on the Dashboard)")
            ctx.check()
            with SessionLocal() as s:
                st = s.get(CaptchaWait, wid).status
            if st == "gave_up":
                break
            page = state(sid)
            if st == "solved" or (page.get("open") and page.get("html") and not is_captcha(page)):
                if not is_captcha(page):
                    result = page
                    break
            time.sleep(2)
    finally:
        with SessionLocal() as s:
            w = s.get(CaptchaWait, wid)
            if w and w.status == "waiting":
                w.status = "solved" if result else "gave_up"
            if w:
                w.ended_at = datetime.utcnow()
            s.commit()
    if result:
        ctx.trace("note", url, text=f"CAPTCHA on {label(engine)} solved by a person — the search goes on")
    return result


# ---------- the search ----------

def discover(ctx, group, query: str, crawl_pages, trace_search):
    """Browser search for one request. `crawl_pages` and `trace_search` come from jobs.py."""
    from . import methods
    from .crawl import skip
    cfg = settings()
    opts = methods.options(group, "browser")
    want = max(1, int(opts.get("want") or 20))
    max_pages = max(1, int(opts.get("max_pages") or 5)) * (1 + max(0, getattr(ctx, "deeper", 0)))
    max_minutes = max(1, int(opts.get("max_minutes") or 15))
    engines = [e for e in (opts.get("engines") or cfg["engines"]) if e in ENGINES]
    start, start_saved = time.time(), ctx.stats["saved"]
    seen: set = set()
    done = 0
    with SessionLocal() as s:
        from .db import Job
        job = s.get(Job, ctx.job_id) if ctx.job_id else None
        owner = job.user_id if job else None
    usable = []
    for e in engines:
        until = paused_until(cfg, e)
        if until:
            ctx.notes.append(f"Browser search: {label(e)} is paused until {until:%H:%M} UTC after a CAPTCHA.")
        else:
            usable.append(e)
    if not usable:
        ctx.notes.append("Browser search: no search engine available right now (switched off or paused).")
        return
    for engine in usable:
        sid = f"eng-{engine}"
        for pageno in range(1, max_pages + 1):
            if ctx.should_stop() or ctx.stats["saved"] - start_saved >= want:
                return
            if time.time() - start > max_minutes * 60:
                ctx.notes.append(f"Browser search stopped after {max_minutes} minutes (directory setting).")
                return
            if searches_last_hour(engine) >= int(cfg["per_hour"]):
                ctx.notes.append(f"Browser search: {label(engine)} reached {cfg['per_hour']} searches this hour.")
                break
            last = last_search_at(engine)
            if last:
                gap = float(cfg["pause"]) - (datetime.utcnow() - last).total_seconds()
                if gap > 0:
                    ctx.step("searching", f"Browser search: a {int(gap)} s pause before the next {label(engine)} search")
                    time.sleep(min(gap, float(cfg["pause"])))
            url = engine_url(engine, query, pageno)
            ctx.step("searching", f"Browser search on {label(engine)}: {query}" + (f" (page {pageno})" if pageno > 1 else ""))
            try:
                page = open_page(sid, url)
            except (httpx.HTTPError, ValueError) as e:
                EN.record(query, pageno, [f"browser:{engine}"], {}, {f"browser:{engine}": f"browser error {type(e).__name__}"},
                          ctx.job_id)
                ctx.trace("error", url, error=f"Browser search: {type(e).__name__}: {e}")
                break
            if is_captcha(page):
                EN.record(query, pageno, [f"browser:{engine}"], {}, {f"browser:{engine}": "CAPTCHA"}, ctx.job_id)
                page = wait_for_person(ctx, engine, sid, url, owner)
                if page is None:
                    pause_engine(engine, float(cfg["captcha_hours"]))
                    ctx.notes.append(f"Browser search: nobody solved the CAPTCHA on {label(engine)} in time, so it "
                                     f"is paused for {cfg['captcha_hours']} hours.")
                    break
            links = result_links(page.get("html") or "")
            EN.record(query, pageno, [f"browser:{engine}"], {f"browser:{engine}": len(links)}, {}, ctx.job_id)
            trace_search(ctx, f"[{label(engine)} in the browser] {query}",
                         [{"url": u, "engines": [f"{label(engine)} (browser)"]} for u in links], page=pageno)
            queue = []
            for u in links:
                ctx.stats["results"] += 1
                if u not in seen and not skip(u):
                    seen.add(u)
                    queue.append((u, 0))
            if queue:
                done = crawl_pages(ctx, group.id, query, "browser", queue, seen, done)
            if not links:
                break
