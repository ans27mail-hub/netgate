"""Requests: start searches, and pause / resume / stop / delete / reject / run them again."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select

from .. import control, methods
from ..auth import can
from ..db import Group, InboxItem, Job, JobTrace, Keyword, Record, RejectedKeyword, SessionLocal, User
from .common import (Forbidden, all_groups, back, can_control, current_user, flash, go, jobs_clause,
                     keyword_blocked, render, require, start_job, templates)

router = APIRouter()


def _tab_clause(tab: str):
    if tab == "deleted":
        return Job.deleted_at.is_not(None)
    base = Job.deleted_at.is_(None)
    states = {"waiting": control.WAITING, "running": control.RUNNING, "paused": {"paused"}, "done": {"done"},
              "failed": {"failed"}, "stopped": {"stopped"}, "rejected": {"rejected"}}
    if tab in states:
        return base & Job.status.in_(list(states[tab]))
    return base


@router.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request, tab: str = "all", dir: str = "", kind: str = "", who: str = "", q: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        tab = tab if tab in dict(control.STATUS_TABS) else "all"
        visible = jobs_clause(user)
        counts = {t: s.scalar(select(func.count(Job.id)).where(visible, _tab_clause(t))) for t, _ in control.STATUS_TABS}
        stmt = select(Job).where(visible, _tab_clause(tab))
        if dir.isdigit():
            stmt = stmt.where(Job.group_id == int(dir))
        if kind in ("discover", "enrich", "night"):
            stmt = stmt.where(Job.kind.in_(["request", "keyword"]) if kind == "discover" else Job.kind == kind)
        if who.isdigit():
            stmt = stmt.where(Job.user_id == int(who))
        if q.strip():
            stmt = stmt.where(or_(Job.query.ilike(f"%{q.strip()}%"), Job.message.ilike(f"%{q.strip()}%")))
        jobs = s.scalars(stmt.order_by(Job.id.desc()).limit(200)).all()
        users = {u.id: u.username for u in s.scalars(select(User)).all()}
        group_names = {g.id: g.name for g in all_groups(s)}
        rejected = s.scalars(select(RejectedKeyword).order_by(RejectedKeyword.at.desc()).limit(200)).all() \
            if tab == "rejected" else []
        return render(request, s, user, "requests.html", active_nav="requests", help="requests", jobs=jobs,
                      tab=tab, counts=counts, users=users, group_names=group_names, f_dir=dir, f_kind=kind,
                      f_who=who, q=q, can_control=lambda j: can_control(user, j), rejected=rejected,
                      groups=all_groups(s))


ACTIONS = {"pause", "resume", "stop", "delete", "undelete", "reject", "restore", "again"}


def _do(s, user, job, action: str, reason: str = "") -> bool:
    if action == "restore" and not can(user, "reject_list") and job.user_id != user.id:
        return False
    if action == "pause":
        return control.pause(s, job)
    if action == "resume":
        return control.resume(s, job)
    if action == "stop":
        return control.stop(s, job)
    if action == "delete":
        return control.delete(s, job)
    if action == "undelete":
        return control.undelete(s, job)
    if action == "reject":
        return control.reject(s, job, reason, user)
    if action == "restore":
        return control.restore(s, job)
    if action == "again":
        if job.kind in control.DISCOVER_KINDS:
            blocked, _ = keyword_blocked(s, job.query, job.group_id)
            if blocked:
                return False
        control.run_again(s, job, user)
        return True
    return False


@router.post("/requests/{jid}/{action}")
def job_action(request: Request, jid: int, action: str, reason: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        job = s.get(Job, jid)
        if not job or action not in ACTIONS:
            return go("/requests")
        if not can_control(user, job):
            raise Forbidden
        ok = _do(s, user, job, action, reason)
        s.commit()
        labels = {"pause": "Pausing", "resume": "Resumed", "stop": "Stopping", "delete": "Moved to Deleted",
                  "undelete": "Restored", "reject": "Rejected — the keyword is on the reject list",
                  "restore": "Keyword taken off the reject list", "again": "Started again"}
        flash(request, f"{labels[action]}: {job.query}" if ok else
              f"Couldn't {action} “{job.query}” right now (status: {job.status}).", not ok)
    return back(request, "/requests")


@router.post("/requests/bulk-reject")
async def bulk_reject(request: Request):
    return await bulk(request, "reject")


@router.post("/requests/bulk")
async def bulk(request: Request, forced: str = ""):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    action = forced or str(form.get("action") or "")
    reason = str(form.get("reason") or "")
    with SessionLocal() as s:
        user = current_user(s, request)
        n = 0
        for job in s.scalars(select(Job).where(Job.id.in_(ids or [-1]))).all():
            if action in ACTIONS and can_control(user, job) and _do(s, user, job, action, reason):
                n += 1
        s.commit()
        flash(request, f"{n} of {len(ids)} request{'s' if len(ids) != 1 else ''}: {action}." if ids
              else "Tick one or more requests first.", not ids)
    return back(request, "/requests")


@router.post("/requests/pause-all")
def pause_all(request: Request, resume: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        if not can(user, "requests_own") and not can(user, "requests_all"):
            raise Forbidden
        n = 0
        stmt = select(Job).where(Job.deleted_at.is_(None))
        if resume:
            stmt = stmt.where(Job.status == "paused")
        else:
            stmt = stmt.where(Job.status.in_(list(control.RUNNING | control.WAITING)))
        for job in s.scalars(stmt).all():
            if not can_control(user, job):
                continue
            if (control.resume(s, job) if resume else control.pause(s, job)):
                n += 1
        s.commit()
        flash(request, (f"Resumed {n} request{'s' if n != 1 else ''}." if resume else
                        f"Pausing {n} request{'s' if n != 1 else ''}. Running ones finish their current page first."))
    return back(request, "/requests")


@router.get("/requests/{jid}/debug", response_class=HTMLResponse)
def debug(request: Request, jid: int, kind: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "debug")
        job = s.get(Job, jid)
        if not job:
            return go("/requests")
        stmt = select(JobTrace).where(JobTrace.job_id == jid)
        if kind:
            stmt = stmt.where(JobTrace.kind == kind)
        rows = s.scalars(stmt.order_by(JobTrace.id).limit(500)).all()
        kinds = dict(s.execute(select(JobTrace.kind, func.count(JobTrace.id)).where(JobTrace.job_id == jid)
                               .group_by(JobTrace.kind)).all())
        new_items = s.scalars(select(InboxItem).where(InboxItem.job_id == jid).limit(200)).all()
        recs = {r.id: r for r in s.scalars(select(Record).where(Record.id.in_([i.record_id for i in new_items] or [-1])))}
        return render(request, s, user, "debug.html", active_nav="requests", help="developer", job=job, rows=rows,
                      kinds=kinds, f_kind=kind, new_items=new_items, recs=recs,
                      group_names={g.id: g.name for g in all_groups(s)})


@router.get("/activity", response_class=HTMLResponse)
def activity(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        jobs = s.scalars(select(Job).where(jobs_clause(user), Job.deleted_at.is_(None))
                         .order_by(Job.id.desc()).limit(8)).all()
        running = sum(1 for j in jobs if j.status in control.RUNNING | control.WAITING)
        return templates.TemplateResponse(request, "_activity.html", {"jobs": jobs, "running": running,
                                                                     "user": user})


# ---------- starting searches ----------

def _blocked_message(request, s, text, gid) -> bool:
    blocked, similar = keyword_blocked(s, text, gid)
    if blocked:
        flash(request, f"“{text}” is on the reject list ({blocked.reason or 'no reason given'}). "
                       "Restore it from Requests → Rejected to search it again.", True)
        return True
    if similar:
        flash(request, f"Started. Note: it is similar to rejected keyword(s): "
                       + ", ".join(f"“{r.text}”" for r in similar[:3]) + ".")
    return False


@router.post("/jobs")
async def create_job(request: Request):
    form = await request.form()
    query = str(form.get("query") or "").strip()
    gid = int(form.get("group_id") or 0)
    use = [m for m in form.getlist("methods") if m in methods.FIND_METHODS]
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "request", gid)
        group = s.get(Group, gid)
        if not group or not query:
            flash(request, "Choose a directory and describe what to look for.", True)
            return back(request, "/inbox")
        if _blocked_message(request, s, query, gid):
            return back(request, "/inbox")
        use = [m for m in use if m in methods.enabled_find_methods(group)] or None
        start_job(s, user, "request", query, gid, params={"methods": use} if use else {})
        if not request.session.get("flash"):
            flash(request, f"Discovery started for {group.name}. New companies appear in the Inbox as they are found.")
    return back(request, "/inbox")


@router.post("/groups/{gid}/keywords/{kid}/run")
def run_keyword(request: Request, gid: int, kid: int, method: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        kw, group = s.get(Keyword, kid), s.get(Group, gid)
        if kw and kw.group_id == gid and not _blocked_message(request, s, kw.text, gid):
            use = [method] if method in methods.enabled_find_methods(group) else methods.keyword_methods(group, kw)
            start_job(s, user, "keyword", kw.text, gid, params={"keyword_id": kw.id, "methods": use})
            if not request.session.get("flash"):
                flash(request, f"Discovering “{kw.text}” with {', '.join(methods.METHODS[m]['name'] for m in use)}. "
                               "Results go to the Inbox.")
    return back(request, "/inbox")


@router.post("/groups/{gid}/keywords/run-all")
def run_all_keywords(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "keywords", gid)
        group = s.get(Group, gid)
        n = skipped = 0
        for kw in (group.keywords if group else []):
            if control.rejected_entry(s, kw.text, gid):
                skipped += 1
                continue
            start_job(s, user, "keyword", kw.text, gid,
                      params={"keyword_id": kw.id, "methods": methods.keyword_methods(group, kw)})
            n += 1
        flash(request, f"Queued {n} keyword search(es)." + (f" {skipped} skipped (on the reject list)." if skipped else ""))
    return back(request, f"/d/{gid}")

