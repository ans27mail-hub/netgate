"""Request controls (pause, resume, stop, delete, reject, run again) and the keyword reject list.

Requests are a separate layer: deleting or rejecting a request never changes contacts or their data.
A running job checks `Job.control` between pages, so Pause / Stop take effect within a few seconds.
"""
import os
import re
from datetime import datetime, timedelta

from sqlalchemy import select

from .db import Job, NightRun, RejectedKeyword

WAITING = {"queued"}
RUNNING = {"running", "searching", "crawling", "extracting", "pausing", "stopping"}
STATUS_TABS = [
    ("all", "All"), ("running", "Running"), ("waiting", "Waiting"), ("paused", "Paused"), ("done", "Done"),
    ("failed", "Failed"), ("stopped", "Stopped"), ("rejected", "Rejected"), ("deleted", "Deleted"),
]
DISCOVER_KINDS = {"request", "keyword"}
KIND_LABELS = {"request": "Discover", "keyword": "Discover", "enrich": "Enrich", "night": "Night"}
STOP_WORDS = {"the", "a", "an", "of", "in", "for", "and", "&", "to", "on", "with", "top", "best", "list", "lists"}


def tab_of(job) -> str:
    if job.deleted_at:
        return "deleted"
    if job.status in WAITING:
        return "waiting"
    if job.status in RUNNING:
        return "running"
    return job.status if job.status in {"paused", "done", "failed", "stopped", "rejected"} else "running"


def actions(job) -> list[str]:
    """Buttons for a request, in order."""
    tab = tab_of(job)
    discover = job.kind in DISCOVER_KINDS
    return {
        "waiting": ["pause", "stop", "delete"] + (["reject"] if discover else []),
        "running": ([] if job.control else ["pause", "stop"]) + (["reject"] if discover and not job.control else []),
        "paused": ["resume", "stop", "delete"] + (["reject"] if discover else []),
        "done": ["again", "delete"] + (["reject"] if discover else []),
        "failed": ["again", "delete"] + (["reject"] if discover else []),
        "stopped": ["again", "delete"] + (["reject"] if discover else []),
        "rejected": ["restore", "delete"],
        "deleted": ["undelete"],
    }.get(tab, [])


# ---------- reject list ----------

def norm_keyword(text: str) -> str:
    """'Leather Gloves Manufacturers' and 'manufacturer of leather glove' -> same key."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = set()
    for w in words:
        if w in STOP_WORDS:
            continue
        if len(w) > 3 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return " ".join(sorted(out))


def rejected_entry(s, text: str, group_id: int | None):
    norm = norm_keyword(text)
    if not norm:
        return None
    for r in s.scalars(select(RejectedKeyword).where(RejectedKeyword.norm == norm)).all():
        if r.group_id is None or r.group_id == group_id:
            return r
    return None


def similar_rejected(s, text: str, group_id: int | None) -> list:
    """Rejected keywords that share most words with this one (a warning, not a block)."""
    a = set(norm_keyword(text).split())
    out = []
    if not a:
        return out
    for r in s.scalars(select(RejectedKeyword)).all():
        if r.group_id not in (None, group_id):
            continue
        b = set((r.norm or "").split())
        if b and a != b and len(a & b) / len(a | b) >= 0.5:
            out.append(r)
    return out


def reject_keyword(s, text: str, group_id: int | None, reason: str, user, job_id: int | None = None):
    if rejected_entry(s, text, group_id):
        return
    s.add(RejectedKeyword(text=text[:300], norm=norm_keyword(text), group_id=group_id, reason=(reason or "")[:200],
                          user_id=user.id if user else None, job_id=job_id))


def unreject_keyword(s, text: str, group_id: int | None):
    norm = norm_keyword(text)
    for r in s.scalars(select(RejectedKeyword).where(RejectedKeyword.norm == norm)).all():
        if r.group_id is None or r.group_id == group_id:
            s.delete(r)


# ---------- queue ----------

_queues: dict = {}


def queue(name: str = "netgate"):
    if name not in _queues:
        from redis import Redis
        from rq import Queue
        _queues[name] = Queue(name, connection=Redis.from_url(os.environ["REDIS_URL"]))
    return _queues[name]


def enqueue_job(job):
    from .jobs import run_job
    if job.kind == "night":
        queue("netgate-night").enqueue(run_job, job.id, run_id=(job.params or {}).get("run_id"),
                                       job_timeout=14 * 3600)
    else:
        queue().enqueue(run_job, job.id, keyword_id=(job.params or {}).get("keyword_id"), job_timeout=3 * 3600)


# ---------- actions ----------

def pause(s, job) -> bool:
    if job.status in WAITING:
        job.status, job.message = "paused", "Paused before it started"
        return True
    if job.status in RUNNING and not job.control:
        job.control, job.status = "pause", "pausing"
        return True
    return False


def resume(s, job) -> bool:
    if job.status != "paused" or job.deleted_at:
        return False
    job.status, job.control, job.message = "queued", "", "Waiting to continue"
    if job.kind == "night":
        run = s.get(NightRun, (job.params or {}).get("run_id"))
        if run:
            run.status = "running"
    s.commit()
    enqueue_job(job)
    return True


def stop(s, job, reject: bool = False) -> bool:
    final = "rejected" if reject else "stopped"
    if job.status in WAITING or job.status == "paused":
        job.message = "Stopped before it started" if job.status in WAITING else (job.message or "Stopped")
        job.status, job.finished_at = final, datetime.utcnow()
        return True
    if job.status in RUNNING:
        job.control, job.status = "stop", "stopping"
        if reject:
            job.params = {**(job.params or {}), "reject": True}
        return True
    if reject and job.status in {"done", "failed", "stopped"}:
        job.status = "rejected"
        return True
    return False


def reject(s, job, reason: str, user) -> bool:
    if job.kind not in DISCOVER_KINDS:
        return False
    reject_keyword(s, job.query, job.group_id, reason, user, job.id)
    job.params = {**(job.params or {}), "reject_reason": reason}
    return stop(s, job, reject=True)


def restore(s, job) -> bool:
    """A rejected request: take its keyword off the reject list."""
    if job.status != "rejected":
        return False
    unreject_keyword(s, job.query, job.group_id)
    job.status = "stopped"
    return True


def delete(s, job) -> bool:
    if job.status in RUNNING or job.deleted_at:
        return False
    if job.status in WAITING:
        job.status = "stopped"
    job.deleted_at = datetime.utcnow()
    return True


def undelete(s, job) -> bool:
    if not job.deleted_at:
        return False
    job.deleted_at = None
    return True


def run_again(s, job, user):
    new = Job(query=job.query, group_id=job.group_id, kind=job.kind if job.kind != "night" else "request",
              user_id=user.id if user else job.user_id, record_id=job.record_id, stats={},
              params={k: v for k, v in (job.params or {}).items() if k in ("keyword_id", "method", "steps")})
    s.add(new)
    s.commit()
    enqueue_job(new)
    return new


def purge_deleted(s, days: int = 30, trace_days: int = 14) -> int:
    """Deleted requests leave the bin after 30 days (contacts keep their data; their link is cleared).
    Debug traces are kept 14 days."""
    from .db import AppLog, JobTrace
    old = s.scalars(select(Job).where(Job.deleted_at.is_not(None),
                                      Job.deleted_at < datetime.utcnow() - timedelta(days=days))).all()
    for j in old:
        s.delete(j)
    s.query(JobTrace).filter(JobTrace.at < datetime.utcnow() - timedelta(days=trace_days)).delete(
        synchronize_session=False)
    s.query(AppLog).filter(AppLog.at < datetime.utcnow() - timedelta(days=60)).delete(synchronize_session=False)
    return len(old)
