"""Search engines (v0.8): which SearXNG engines NetGate uses, and whether each one works or blocks.

SearXNG asks several search engines (Google, Bing, DuckDuckGo …) for every search. NetGate:
- chooses the engines with SearXNG's `engines=` parameter, so turning one off needs no SearXNG config change;
- logs every search in `search_log`: links per engine, and the engines SearXNG reports as unresponsive
  (CAPTCHA, access denied, too many requests, timeout);
- builds each engine's status from that log: Working, Blocking (since when), Error, Not Used Yet.

Paid backup search keys (Brave, Google, Serper) are left for later (owner, 18 Oct 2026).
"""
import re
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from .db import SearchLog, SessionLocal, get_setting, log, set_setting

SETTING = "search_engines"     # {"set": true, "on": ["bing", "duckduckgo", …]} — absent = SearXNG's own choice
KEEP_DAYS = 30
RECENT_DAYS = 7

# Engines that search the whole web (the useful ones for finding companies), in the order they are shown.
KNOWN = [
    ("google", "Google", "Best results, but often blocks automated searches (CAPTCHA)."),
    ("bing", "Bing", "Good results; blocks less often."),
    ("duckduckgo", "DuckDuckGo", "Uses Bing's index; sometimes asks for a CAPTCHA."),
    ("brave", "Brave", "Its own index; limits how many searches per hour."),
    ("startpage", "Startpage", "Google results through a privacy proxy; can block too."),
    ("qwant", "Qwant", "European engine; sometimes unavailable from some countries."),
    ("mojeek", "Mojeek", "Small independent index; rarely blocks."),
    ("yahoo", "Yahoo", "Uses Bing's index."),
    ("presearch", "Presearch", "Small engine; mixed results."),
    ("wikipedia", "Wikipedia", "Encyclopedia pages only — rarely useful for companies."),
]
LABELS = {k: label for k, label, _ in KNOWN}
NOTES = {k: note for k, _, note in KNOWN}
FALLBACK_DEFAULT = ["google", "bing", "duckduckgo", "brave", "startpage", "wikipedia"]
BLOCK_WORDS = re.compile(r"captcha|access denied|denied|too many|suspend|forbidden|blocked|403|429", re.I)


def label(name: str) -> str:
    if name.startswith("browser:"):
        return LABELS.get(name[8:], name[8:].title()) + " (browser)"
    return LABELS.get(name, name.replace("_", " ").title())


# ---------- SearXNG's engine list ----------

_config_cache: dict = {"at": 0.0, "value": None}


def searx_engines(force: bool = False) -> list[dict] | None:
    """[{name, enabled}] of SearXNG's web ('general') engines, from its /config page; None when unreachable."""
    from .crawl import SEARXNG_URL
    if not force and _config_cache["value"] is not None and time.time() - _config_cache["at"] < 600:
        return _config_cache["value"]
    try:
        r = httpx.get(f"{SEARXNG_URL}/config", timeout=5)
        r.raise_for_status()
        out = [{"name": e.get("name"), "enabled": bool(e.get("enabled"))}
               for e in r.json().get("engines", []) if e.get("name") and "general" in (e.get("categories") or [])]
    except (httpx.HTTPError, ValueError):
        out = None
    if out is not None:
        _config_cache.update(at=time.time(), value=out)
    return out


def default_on(cfg: list[dict] | None) -> list[str]:
    """The engines SearXNG uses when NetGate doesn't choose."""
    if cfg is None:
        return list(FALLBACK_DEFAULT)
    return [e["name"] for e in cfg if e["enabled"]]


def catalogue(cfg: list[dict] | None) -> list[str]:
    """Engines to show: the known web engines plus any other web engine SearXNG switches on by itself."""
    names = [k for k, _, _ in KNOWN]
    if cfg is not None:
        have = {e["name"] for e in cfg}
        names = [n for n in names if n in have] + [e["name"] for e in cfg if e["enabled"] and e["name"] not in names]
    return names


# ---------- the owner's choice ----------

_choice_cache: dict = {"at": 0.0, "value": None, "loaded": False}


def saved(s) -> dict:
    return get_setting(s, SETTING, {}) or {}


def chosen() -> list[str] | None:
    """Engines to ask, or None for SearXNG's own choice. Re-read at most once a minute."""
    if not _choice_cache["loaded"] or time.time() - _choice_cache["at"] > 60:
        try:
            with SessionLocal() as s:
                cfg = saved(s)
            value = list(cfg.get("on") or []) if cfg.get("set") and cfg.get("on") else None
        except Exception:
            value = None
        _choice_cache.update(at=time.time(), value=value, loaded=True)
    return _choice_cache["value"]


def save_choice(s, on: list[str] | None):
    """on=None goes back to SearXNG's own choice."""
    set_setting(s, SETTING, {"set": True, "on": on} if on else {})
    _choice_cache.update(loaded=False)


# ---------- the log ----------

def record(query: str, pageno: int, asked: list[str] | None, results: dict, errors: dict, job_id: int | None,
           test: bool = False):
    """Write one search to the log. Never raises: logging must not stop a search."""
    try:
        if not asked:
            asked = default_on(_config_cache["value"]) if _config_cache["value"] is not None else []
        with SessionLocal() as s:
            s.add(SearchLog(query=(query or "")[:500], pageno=pageno, asked=list(asked or []), results=results,
                            errors={k: str(v)[:200] for k, v in (errors or {}).items()},
                            total=sum(results.values()), job_id=job_id, test=test))
            s.commit()
    except Exception as e:  # noqa: BLE001
        log("warning", "search", f"Could not log a search: {type(e).__name__}: {e}")


def is_block(reason: str) -> bool:
    return bool(BLOCK_WORDS.search(reason or ""))


def status(s, names: list[str]) -> dict:
    """name -> {state, since, reason, last_ok, searches, results, avg, errors} from the last 30 days of searches.
    state: working / blocking / error / unused."""
    rows = s.scalars(select(SearchLog).where(SearchLog.at >= datetime.utcnow() - timedelta(days=KEEP_DAYS))
                     .order_by(SearchLog.id.desc()).limit(3000)).all()
    recent = datetime.utcnow() - timedelta(days=RECENT_DAYS)
    out = {}
    for n in names:
        info = {"state": "unused", "since": None, "reason": "", "last_ok": None, "last_used": None,
                "searches": 0, "results": 0, "errors": 0, "avg": 0.0}
        streak_open = True
        for r in rows:   # newest first
            used = n in (r.asked or []) or n in (r.results or {}) or n in (r.errors or {})
            if not used:
                continue
            info["last_used"] = info["last_used"] or r.at
            failed = n in (r.errors or {})
            if r.at >= recent:
                info["searches"] += 1
                info["results"] += int((r.results or {}).get(n, 0))
                info["errors"] += int(failed)
            if streak_open:
                if failed:
                    reason = r.errors[n]
                    if info["state"] == "unused":
                        info["state"], info["reason"] = ("blocking" if is_block(reason) else "error"), reason
                    info["since"] = r.at          # moves back to the first failure of this run of failures
                else:
                    if info["state"] == "unused":
                        info["state"] = "working"
                    info["last_ok"] = r.at
                    streak_open = False
            elif not failed and not info["last_ok"]:
                info["last_ok"] = r.at
        info["avg"] = round(info["results"] / info["searches"], 1) if info["searches"] else 0.0
        out[n] = info
    return out


def problems(s) -> list[tuple[str, dict]]:
    """Engines that are switched on but blocking or failing right now (for the Dashboard)."""
    cfg = saved(s)
    on = list(cfg.get("on") or []) if cfg.get("set") else default_on(_config_cache["value"])
    if not on:
        return []
    st = status(s, on)
    return [(n, st[n]) for n in on if st[n]["state"] in ("blocking", "error")]


def purge(s, days: int = KEEP_DAYS) -> int:
    return s.query(SearchLog).filter(SearchLog.at < datetime.utcnow() - timedelta(days=days)).delete(
        synchronize_session=False)
