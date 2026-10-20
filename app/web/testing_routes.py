"""Testing Guide (v1.0, permission “Testing Guide”): checklists to test NetGate by hand, saved test runs per
version, a read-only Quick Health Check, and the hidden Test Directory that one button empties."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import delete, func, select, text

from .. import crawl, engines
from ..control import RUNNING as RUNNING_STATES
from .. import testguide as TG
from ..db import (DEFAULT_METHODS, AIServer, AppLog, Field, Group, InboxItem, Job, Membership, NightRun, Record, SessionLocal, TestRun,
                  TestShot, User, default_fields, log)
from .common import VERSION, Forbidden, current_user, flash, go, render, require, templates

router = APIRouter()
TEST_DIR = "Test Directory"
SHOT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def test_group(s):
    return s.scalar(select(Group).where(Group.is_test).order_by(Group.id).limit(1))


@router.get("/testing", response_class=HTMLResponse)
def testing_home(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "testing")
        runs = s.scalars(select(TestRun).order_by(TestRun.id.desc()).limit(60)).all()
        names = dict(s.execute(select(User.id, User.username)).all())
        lists = TG.checklists()
        tg = test_group(s)
        tcount = s.scalar(select(func.count()).select_from(Membership).where(Membership.group_id == tg.id)) if tg else 0
        tinbox = s.scalar(select(func.count()).select_from(InboxItem).where(InboxItem.group_id == tg.id,
                                                                         InboxItem.status == "new")) if tg else 0
        return render(request, s, user, "testing.html", active_nav="testing", help="testing-guide",
                      runs=[(r, TG.counts(r)) for r in runs], names=names, lists=lists, tg=tg, tcount=tcount,
                      tinbox=tinbox, new_steps=sum(1 for c in lists for st in c["steps"] if st["since"] == VERSION),
                      all_steps=sum(len(c["steps"]) for c in lists))


@router.post("/testing/runs")
async def run_start(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "testing")
        run = TestRun(user_id=user.id, version=VERSION, scope="new" if form.get("scope") == "new" else "all",
                      results={}, notes="")
        s.add(run)
        s.commit()
        return go(f"/testing/runs/{run.id}")


def _run(s, user, rid):
    require(user, "testing")
    run = s.get(TestRun, rid)
    if not run:
        raise Forbidden
    return run


@router.get("/testing/runs/{rid}", response_class=HTMLResponse)
def run_page(request: Request, rid: int, only: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        run = _run(s, user, rid)
        lists = TG.for_scope(run.scope, run.version)
        names = dict(s.execute(select(User.id, User.username)).all())
        shots = {}
        for sid, step in s.execute(select(TestShot.id, TestShot.step).where(TestShot.run_id == run.id)).all():
            shots.setdefault(step, []).append(sid)
        if only == "fail":
            lists = [{**c, "steps": [st for st in c["steps"] if ((run.results or {}).get(st["id"]) or {}).get("ok") == "fail"]}
                     for c in lists]
            lists = [c for c in lists if c["steps"]]
        elif only == "todo":
            lists = [{**c, "steps": [st for st in c["steps"] if not ((run.results or {}).get(st["id"]) or {}).get("ok")]}
                     for c in lists]
            lists = [c for c in lists if c["steps"]]
        full = TG.for_scope(run.scope, run.version)
        return render(request, s, user, "test_run.html", active_nav="testing", help="testing-guide", run=run,
                      lists=lists, n=TG.counts(run, full), names=names, shots=shots, RESULTS=TG.RESULTS, only=only,
                      report=TG.report(run, full, names), mine=run.user_id == user.id or user.is_admin,
                      old_version=run.version != VERSION)


@router.post("/testing/runs/{rid}/step", response_class=HTMLResponse)
async def run_step(request: Request, rid: int):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        run = _run(s, user, rid)
        if run.finished_at:
            raise Forbidden
        step = str(form.get("step") or "")
        known = {st["id"]: (c, st) for c in TG.for_scope(run.scope, run.version) for st in c["steps"]}
        if step not in known:
            raise Forbidden
        TG.set_result(run, step, str(form.get("ok") or ""), str(form.get("note") or "").strip(), user.username)
        up = form.get("shot")
        if up is not None and getattr(up, "filename", ""):
            data = await up.read()
            ctype = (up.content_type or "").lower()
            if ctype in SHOT_TYPES and 0 < len(data) <= 5 * 1024 * 1024:
                s.add(TestShot(run_id=run.id, step=step, mime=ctype, data=data))
        s.commit()
        shots = s.scalars(select(TestShot.id).where(TestShot.run_id == run.id, TestShot.step == step)).all()
        c, st = known[step]
        return templates.TemplateResponse(request, "_test_step.html", {
            "run": run, "st": st, "r": (run.results or {}).get(step) or {}, "shots": shots, "RESULTS": TG.RESULTS,
            "user": user, "saved": True})


@router.get("/testing/shots/{sid}")
def shot(request: Request, sid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "testing")
        row = s.get(TestShot, sid)
        if not row:
            return Response(status_code=404)
        return Response(row.data, media_type=row.mime, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/testing/runs/{rid}/{action}")
async def run_action(request: Request, rid: int, action: str):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        run = _run(s, user, rid)
        if action == "finish":
            run.finished_at = datetime.utcnow()
            run.notes = str(form.get("notes") or run.notes or "").strip()[:4000]
            s.commit()
            n = TG.counts(run)
            flash(request, f"Test run finished: {n['pass']} passed, {n['fail']} failed, {n['todo']} not done.")
            return go(f"/testing/runs/{rid}")
        if action == "reopen":
            run.finished_at = None
            s.commit()
            return go(f"/testing/runs/{rid}")
        if action == "notes":
            run.notes = str(form.get("notes") or "").strip()[:4000]
            s.commit()
            flash(request, "Notes saved.")
            return go(f"/testing/runs/{rid}")
        if action == "delete":
            if not (run.user_id == user.id or user.is_admin):
                raise Forbidden
            s.delete(run)
            s.commit()
            flash(request, "Test run deleted.")
            return go("/testing")
    raise Forbidden


# ---------- Quick Health Check (reads only; changes nothing) ----------

def _http_ok(url: str) -> bool:
    import httpx
    return httpx.get(url, timeout=4).status_code < 500


def health(s) -> list[dict]:
    rows = []

    def add(name, ok, detail, tone=None):
        rows.append({"name": name, "tone": tone or ("green" if ok else "red"), "detail": detail})

    try:
        s.execute(text("SELECT 1"))
        n = s.scalar(select(func.count(Record.id)))
        add("Database", True, f"answers · {n} contacts")
    except Exception as e:  # noqa: BLE001
        add("Database", False, f"{type(e).__name__}")
    try:
        from ..control import queue
        q = queue()
        q.connection.ping()
        add("Queue (Redis)", True, f"answers · {len(q)} job{'s' if len(q) != 1 else ''} waiting")
    except Exception as e:  # noqa: BLE001
        add("Queue (Redis)", False, f"not reachable ({type(e).__name__})")
    servers = s.scalars(select(AIServer).where(AIServer.enabled).order_by(AIServer.id)).all()
    checks = [("Browser (renderer)", lambda: crawl.renderer_status())]
    for sv in servers[:3]:
        if sv.kind == "ollama":
            checks.append((f"AI server ({sv.name})", lambda u=sv.url: _http_ok(u.rstrip("/") + "/api/tags")))
    checks.append(("Search (SearXNG)", lambda: _http_ok(f"{crawl.SEARXNG_URL}/healthz")))

    def run(c):
        try:
            return c[0], bool(c[1]())
        except Exception:  # noqa: BLE001
            return c[0], False
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, ok in pool.map(run, checks):
            add(name, ok, "answers" if ok else "not answering")
    if not servers:
        add("AI server", False, "none set up", "amber")
    stuck = s.scalar(select(func.count(Job.id)).where(Job.status.in_(list(RUNNING_STATES)), Job.deleted_at.is_(None),
                                                      Job.updated_at < datetime.utcnow() - timedelta(minutes=30))) or 0
    add("Requests", not stuck, f"{stuck} running request{'s' if stuck != 1 else ''} with no progress for 30 minutes"
        if stuck else "none stuck", "amber" if stuck else None)
    errs = s.scalar(select(func.count(AppLog.id)).where(AppLog.level == "error",
                                                        AppLog.at > datetime.utcnow() - timedelta(hours=24))) or 0
    add("Errors (last 24 hours)", not errs, f"{errs} in the log" if errs else "none", "amber" if errs else None)
    blocked = engines.problems(s)
    add("Search engines", not blocked, f"{len(blocked)} blocking" if blocked else "none blocking",
        "amber" if blocked else None)
    last = s.scalar(select(NightRun).order_by(NightRun.id.desc()).limit(1))
    add("Last night run", True, f"{last.night_date:%d %b} · {last.status}" if last else "none yet", "green" if last else "amber")
    return rows


@router.get("/testing/health", response_class=HTMLResponse)
def health_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "testing")
        return render(request, s, user, "test_health.html", active_nav="testing", help="testing-guide",
                      rows=health(s), at=datetime.utcnow())


# ---------- the hidden Test Directory ----------

@router.post("/testing/test-directory/{action}")
def test_directory(request: Request, action: str):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "testing")
        tg = test_group(s)
        if action == "create":
            if not tg:
                name = TEST_DIR
                if s.scalar(select(Group).where(Group.name == name)):
                    name = "Test Directory (hidden)"
                tg = Group(name=name, is_test=True, position=9999, owner_id=user.id, card={},
                           description="Hidden directory for the Testing Guide. Empty it with one button.",
                           instructions="Companies that make leather gloves or motorbike clothing.",
                           methods=dict(DEFAULT_METHODS), night_discover=False, night_enrich=False)
                tg.fields = default_fields() + [Field(name="Contact email", key="contact_email", type="email",
                                                      list=True, position=4)]
                s.add(tg)
                s.commit()
                log("info", "web", f"Test Directory made by {user.username}")
                flash(request, "Test Directory made. Only people with the Testing Guide permission see it.")
            return go(f"/d/{tg.id}")
        if action == "empty" and tg:
            ids = s.scalars(select(Membership.record_id).where(Membership.group_id == tg.id)).all()
            inbox_ids = s.scalars(select(InboxItem.record_id).where(InboxItem.group_id == tg.id)).all()
            elsewhere = set(s.scalars(select(Membership.record_id).where(
                Membership.record_id.in_(list(ids) + list(inbox_ids) or [-1]), Membership.group_id != tg.id)).all())
            s.execute(delete(InboxItem).where(InboxItem.group_id == tg.id))
            s.execute(delete(Membership).where(Membership.group_id == tg.id))
            gone = [i for i in set(ids) | set(inbox_ids) if i not in elsewhere]
            # a company still waiting in another directory's Inbox is kept too
            keep = set(s.scalars(select(InboxItem.record_id).where(InboxItem.record_id.in_(gone or [-1]))).all())
            gone = [i for i in gone if i not in keep]
            if gone:
                s.execute(delete(Record).where(Record.id.in_(gone)))
            jobs = s.scalars(select(Job).where(Job.group_id == tg.id, Job.deleted_at.is_(None))).all()
            for j in jobs:
                if j.status in RUNNING_STATES:
                    j.control = "stop"
                j.deleted_at = datetime.utcnow()
            s.commit()
            log("info", "web", f"Test Directory emptied by {user.username}: {len(gone)} contacts deleted")
            flash(request, f"Test Directory emptied: {len(gone)} test contact{'s' if len(gone) != 1 else ''} deleted, "
                           f"{len(jobs)} request{'s' if len(jobs) != 1 else ''} removed. Contacts that are also in "
                           "another directory were kept there.")
            return go("/testing")
    return go("/testing")
