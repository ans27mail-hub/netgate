"""The list of pages read (v0.9). Every page NetGate reads is written to `pages_read` with what was found on it.

- Discovery skips a list page that was read for the same directory in the last N days (Settings → Crawler,
  “Read list pages again after”, 0 = always read again), and always skips pages read by earlier tries of the
  same request (Edit and Run Again).
- Enrich only opens pages it hasn't read for that company; for pages read before it reuses what code found there
  (emails, phones, social links). “Check all again” reads everything again.
- Debug and the big card show the pages.
Kept permanently: it becomes the base of the Saved Pages part of NetGate.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from .db import PageRead, SessionLocal, log

DEFAULT_REREAD_DAYS = 7
PURPOSES = {"list": "List page", "profile": "Directory profile", "site": "Company website", "other": "Other page"}


def norm(url: str) -> str:
    """The same page with or without a trailing slash or #part counts as one."""
    u = (url or "").split("#")[0].strip()
    return u[:-1] if u.endswith("/") and u.count("/") > 3 else u


def record(page, job_id: int | None, purpose: str, group_id: int | None = None, record_id: int | None = None,
           found: dict | None = None) -> int | None:
    """Write one page read. Returns its id (or None when it could not be written — never stops a job)."""
    try:
        with SessionLocal() as s:
            row = PageRead(url=norm(page.url)[:2000], final_url=(page.final_url or "")[:2000], job_id=job_id,
                           group_id=group_id, record_id=record_id, purpose=purpose[:12], ok=bool(page.ok),
                           chars=len(page.text or ""), rendered=bool(getattr(page, "rendered", False)),
                           found=found or {}, note=(getattr(page, "note", "") or "")[:300])
            s.add(row)
            s.commit()
            return row.id
    except Exception as e:  # noqa: BLE001
        log("warning", "pages", f"Could not record a page read: {type(e).__name__}: {e}")
        return None


def add_found(row_id: int | None, **found):
    """Add what was found on a page (companies, code finds, fields filled) to its row."""
    if not row_id:
        return
    try:
        with SessionLocal() as s:
            row = s.get(PageRead, row_id)
            if row:
                merged = dict(row.found or {})
                for k, v in found.items():
                    if isinstance(v, list) and isinstance(merged.get(k), list):
                        merged[k] = list(dict.fromkeys(merged[k] + v))
                    elif isinstance(v, dict) and isinstance(merged.get(k), dict):
                        merged[k] = {**merged[k], **v}
                    else:
                        merged[k] = v
                row.found = merged
                s.commit()
    except Exception as e:  # noqa: BLE001
        log("warning", "pages", f"Could not update a page read: {type(e).__name__}: {e}")


def read_before_for_list(url: str, group_id: int | None, job_id: int | None, days: int):
    """A list page that needn't be read again: read by this same request (an earlier try) at any time, or for the
    same directory within `days` days. Returns the earlier row, or None."""
    u = norm(url)
    with SessionLocal() as s:
        if job_id:
            row = s.scalar(select(PageRead).where(PageRead.url == u, PageRead.job_id == job_id, PageRead.ok,
                                                  PageRead.purpose == "list").order_by(PageRead.id.desc()).limit(1))
            if row:
                return row
        if days and days > 0:
            since = datetime.utcnow() - timedelta(days=days)
            return s.scalar(select(PageRead).where(PageRead.url == u, PageRead.group_id == group_id, PageRead.ok,
                                                   PageRead.purpose == "list", PageRead.at >= since)
                            .order_by(PageRead.id.desc()).limit(1))
    return None


def read_for_record(record_id: int) -> dict:
    """{url: row} of the pages already read (successfully) for this company, newest first."""
    out = {}
    with SessionLocal() as s:
        for row in s.scalars(select(PageRead).where(PageRead.record_id == record_id, PageRead.ok)
                             .order_by(PageRead.id.desc()).limit(500)).all():
            out.setdefault(row.url, row)
    return out


def for_job(s, job_id: int, limit: int = 300) -> list:
    return s.scalars(select(PageRead).where(PageRead.job_id == job_id).order_by(PageRead.id).limit(limit)).all()


def for_record(s, record_id: int, limit: int = 50) -> list:
    """Pages read for this company (Enrich) and list / profile pages that found it."""
    return s.scalars(select(PageRead).where(PageRead.record_id == record_id).order_by(PageRead.id.desc())
                     .limit(limit)).all()


def summary(row) -> str:
    """One line: what was found on a page."""
    f = row.found or {}
    parts = []
    if f.get("companies"):
        n = len(f["companies"])
        parts.append(f"{n} compan{'ies' if n != 1 else 'y'}")
    if f.get("filled"):
        parts.append("filled " + ", ".join(f["filled"][:4]))
    code = f.get("code") or {}
    for k, label in (("emails", "email"), ("phones", "phone")):
        if code.get(k):
            parts.append(f"{len(code[k])} {label}{'s' if len(code[k]) != 1 else ''}")
    if code.get("social"):
        parts.append(", ".join(sorted(code["social"])))
    if f.get("skipped_ai"):
        parts.append("reused")
    if not row.ok:
        return "could not read" + (f" ({row.note})" if row.note else "")
    return " · ".join(parts) or "nothing new"
