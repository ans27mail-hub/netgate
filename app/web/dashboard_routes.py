"""The Dashboard (start page) and the Directories page."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from .. import contacts as C
from .. import backups, control, crawl, ebay, engines
from ..auth import can, own_contacts_only, sees_all_groups
from ..contacts import user_name
from ..db import AIServer, Decision, InboxItem, Job, Membership, NightRun, Record, SessionLocal, User
from ..methods import METHODS, connections
from .common import (ago, can_control, current_user, go, inbox_clause, jobs_clause, last_night, render, require,
                     templates, view_groups, visible_records_clause)

router = APIRouter()

# soft colours for the letter tile of each directory card (background, text)
TILES = [("#eef2fb", "#1e46ab"), ("#fdf0dc", "#7a4a00"), ("#e3f1ea", "#1d5c3d"), ("#f3eefc", "#5b3aa8"),
         ("#fbe9e4", "#8a3216"), ("#e6f3f5", "#155e6b"), ("#f0f2f5", "#3b414c")]
SORTS = [("menu", "Menu Order"), ("name", "Name A–Z"), ("contacts", "Most Contacts"),
         ("inbox", "Most Waiting in Inbox"), ("least", "Least Complete")]


def dir_stats(s, groups, user=None) -> dict:
    """Per directory: contacts, waiting in Inbox, % of fields filled, keywords, last search, top missing field.
    For people who only see their own contacts, everything is counted over their own contacts."""
    ids = [g.id for g in groups] or [-1]
    own = own_contacts_only(user)
    mine = select(Record.id).where(Record.found_by == user.id) if own else None
    cq = select(Membership.group_id, func.count(Membership.record_id)).where(Membership.group_id.in_(ids))
    wq = select(InboxItem.group_id, func.count(InboxItem.id)).where(InboxItem.status == "new",
                                                                   InboxItem.group_id.in_(ids))
    if own:
        cq, wq = cq.where(Membership.record_id.in_(mine)), wq.where(InboxItem.record_id.in_(mine))
    counts = dict(s.execute(cq.group_by(Membership.group_id)).all())
    waiting = dict(s.execute(wq.group_by(InboxItem.group_id)).all())
    last = dict(s.execute(select(Job.group_id, func.max(Job.created_at))
                          .where(Job.group_id.in_(ids), Job.kind.in_(["request", "keyword"]))
                          .group_by(Job.group_id)).all())
    datas: dict = {}
    dq = select(Membership.group_id, Record.data).join(Record, Record.id == Membership.record_id) \
        .where(Membership.group_id.in_(ids))
    if own:
        dq = dq.where(Record.found_by == user.id)
    for gid, data in s.execute(dq).all():
        datas.setdefault(gid, []).append(data or {})
    out = {}
    for g in groups:
        rows, fields = datas.get(g.id, []), list(g.fields)
        filled = total = incomplete = 0
        missing: dict = {}
        for data in rows:
            n = 0
            for f in fields:
                if C.empty(data.get(f.key)):
                    missing[f.name] = missing.get(f.name, 0) + 1
                else:
                    n += 1
            filled, total = filled + n, total + len(fields)
            incomplete += n < len(fields)
        pct = int(round(filled * 100 / total)) if total else 0
        top = max(missing.items(), key=lambda kv: kv[1]) if missing else None
        out[g.id] = {"contacts": counts.get(g.id, 0), "inbox": waiting.get(g.id, 0), "pct": pct,
                     "bar": "good" if pct >= 80 else ("low" if pct < 50 else ""),
                     "keywords": len(g.keywords), "never_run": sum(1 for k in g.keywords if not k.last_run_at),
                     "last": last.get(g.id), "incomplete": incomplete, "top_missing": top,
                     "methods": [METHODS[k] for k in (g.methods or {}) if k in METHODS]}
    return out


# ---------- Dashboard ----------

def _activity(s, user, groups, limit=12) -> list[dict]:
    names = {g.id: g.name for g in groups}
    all_dirs = sees_all_groups(user)
    out = []
    q = select(Decision).order_by(Decision.id.desc()).limit(40)
    if not all_dirs:
        q = q.where(Decision.group_id.in_(list(names) or [-1]))
    if own_contacts_only(user):
        q = q.where(Decision.record_id.in_(select(Record.id).where(Record.found_by == user.id)))
    titles = {}
    decs = s.scalars(q).all()
    rids = [d.record_id for d in decs if d.record_id]
    if rids:
        titles = dict(s.execute(select(Record.id, Record.title).where(Record.id.in_(rids))).all())
    labels = {"accept": ("Accepted", "green"), "reject": ("Rejected", "red"), "restore": ("Restored", "grey"),
              "remove": ("Removed", "grey"), "move": ("Moved", "purple")}
    for d in decs:
        kind, tone = labels.get(d.decision, (d.decision.title(), "grey"))
        who = user_name(s, d.user_id)
        name = titles.get(d.record_id) or (d.snapshot or {}).get("title") or "a contact"
        where = names.get(d.group_id, "a directory")
        if d.decision == "accept":
            text = f"{who} accepted {name} into {where}"
        elif d.decision == "reject":
            text = f"{who} rejected {name} for {where}" + (f" ({d.reason})" if d.reason else "")
        elif d.decision == "move":
            text = f"{who} moved {name} {d.reason} to {where}".replace("  ", " ")
        elif d.decision == "remove":
            text = f"{who} removed {name} from {where}"
        else:
            text = f"{who} restored {name} for {where}"
        out.append({"at": d.at, "kind": kind, "tone": tone, "text": text})
    jq = (select(Job).where(Job.deleted_at.is_(None), Job.finished_at.is_not(None),
                            Job.kind.in_(["request", "keyword", "night"]), jobs_clause(user))
          .order_by(Job.finished_at.desc()).limit(15))
    for j in s.scalars(jq).all():
        if j.kind == "night":
            st = j.stats or {}
            out.append({"at": j.finished_at, "kind": "Night run", "tone": "amber",
                        "text": f"Night run {j.status} · {st.get('saved', 0)} new · {st.get('companies', 0)} enriched"})
        else:
            new = (j.stats or {}).get("saved", j.saved or 0)
            text = f"“{j.query[:80]}” {'finished' if j.status == 'done' else j.status}"
            if j.status == "done":
                text += f" · {new} new in the Inbox"
            out.append({"at": j.finished_at, "kind": "Search", "tone": "blue" if j.status == "done" else "red",
                        "text": text})
    out.sort(key=lambda e: e["at"] or datetime.min, reverse=True)
    return out[:limit]


def _attention(s, user, groups, stats) -> list[dict]:
    """Short list of things worth doing now. tone: red / amber / green."""
    out = []
    if can(user, "backups"):
        warn = backups.warning(s)
        if warn:
            out.append({"tone": "red" if "No backup" in warn or "days old" in warn else "amber", "text": warn,
                        "label": "Backups", "href": "/settings/backups"})
    day = datetime.utcnow() - timedelta(hours=24)
    failed = s.scalar(select(func.count(Job.id)).where(Job.deleted_at.is_(None), Job.status == "failed",
                                                       Job.updated_at >= day, jobs_clause(user)))
    if failed:
        out.append({"tone": "red", "text": f"{failed} request{'s' if failed != 1 else ''} failed in the last 24 hours",
                    "label": "See Requests", "href": "/requests?tab=failed"})
    for name, st in engines.problems(s)[:3]:   # v0.8: a search engine that blocks or doesn't answer
        what = "is blocking searches" if st["state"] == "blocking" else "isn't answering"
        item = {"tone": "red" if st["state"] == "blocking" else "amber",
                "text": f"{engines.label(name)} {what} ({st['reason'][:40]}) — started {ago(st['since'])}"}
        if can(user, "crawler"):
            item.update(label="Search Engines", href="/settings/search-engines")
        out.append(item)
    ebay_dirs = [g.name for g in groups if "ebay" in (g.methods or {})]
    if ebay_dirs and not ebay.ready(connections(s)):
        item = {"tone": "amber", "text": f"eBay keys are not set up — eBay search is skipped in {', '.join(ebay_dirs[:2])}"}
        if can(user, "connections"):
            item.update(label="Add Keys", href="/settings/connections")
        out.append(item)
    gaps = sorted(((stats[g.id]["top_missing"][1], g) for g in groups if stats[g.id]["top_missing"]),
                  key=lambda x: -x[0])
    for n, g in gaps[:2]:
        field = stats[g.id]["top_missing"][0]
        item = {"tone": "amber", "text": f"{g.name}: {n} contact{'s' if n != 1 else ''} without {field}"}
        if can(user, "enrich", g.id):
            item.update(label="Enrich Them", post=f"/groups/{g.id}/enrich-incomplete")
        out.append(item)
    for g in [g for g in groups if stats[g.id]["never_run"]][:2]:
        n = stats[g.id]["never_run"]
        item = {"tone": "amber", "text": f"{g.name}: {n} keyword{'s have' if n != 1 else ' has'} never been run"}
        if can(user, "keywords", g.id):
            item.update(label="Run Now", post=f"/groups/{g.id}/keywords/run-all")
        out.append(item)
    ready = s.scalar(select(func.count(InboxItem.id)).join(Record, Record.id == InboxItem.record_id)
                     .where(InboxItem.status == "new", Record.enrich_runs > 0, inbox_clause(user, groups)))
    if ready and can(user, "review"):
        out.append({"tone": "green", "text": f"{ready} compan{'ies' if ready != 1 else 'y'} in the Inbox "
                                             f"{'are' if ready != 1 else 'is'} enriched and ready to decide",
                    "label": "Review", "href": "/inbox?tab=enriched"})
    return out


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, group: int | None = None):
    if group:   # v0.4 addresses
        return go(f"/d/{group}")
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        groups = view_groups(s, user)
        stats = dir_stats(s, groups, user)
        week = datetime.utcnow() - timedelta(days=7)
        icl = inbox_clause(user, groups)
        inbox_new = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.status == "new", icl)) or 0
        inbox_enriched = s.scalar(select(func.count(InboxItem.id)).join(Record, Record.id == InboxItem.record_id)
                                  .where(InboxItem.status == "new", Record.enrich_runs > 0, icl)) or 0
        vis = visible_records_clause(user, groups)
        contacts = s.scalar(select(func.count(Record.id)).where(vis)) or 0
        added_week = s.scalar(select(func.count(Record.id)).where(vis, Record.accepted_at >= week)) or 0
        dq = select(Decision.decision, func.count(Decision.id)).where(Decision.at >= week)
        if not sees_all_groups(user):
            dq = dq.where(Decision.group_id.in_([g.id for g in groups] or [-1]))
        dec = dict(s.execute(dq.group_by(Decision.decision)).all())
        jc = [Job.deleted_at.is_(None), jobs_clause(user)]
        running = s.scalar(select(func.count(Job.id)).where(Job.status.in_(list(control.RUNNING)), *jc)) or 0
        waiting = s.scalar(select(func.count(Job.id)).where(Job.status.in_(list(control.WAITING)), *jc)) or 0
        failed = s.scalar(select(func.count(Job.id)).where(Job.status == "failed",
                                                           Job.updated_at >= datetime.utcnow() - timedelta(hours=24),
                                                           *jc)) or 0
        night = last_night(s) or s.scalar(select(NightRun).order_by(NightRun.id.desc()).limit(1))
        tiles = [
            {"label": "Inbox Waiting", "value": inbox_new, "sub": f"{inbox_new - inbox_enriched} new · {inbox_enriched} enriched",
             "href": "/inbox"},
            {"label": "Contacts", "value": contacts, "sub": f"+{added_week} added this week", "href": "/contacts"},
            {"label": "Decisions This Week", "value": dec.get("accept", 0) + dec.get("reject", 0),
             "sub": f"{dec.get('accept', 0)} accepted · {dec.get('reject', 0)} rejected", "href": "/inbox"},
            {"label": "Searches", "value": f"{running} running", "sub": f"{waiting} waiting · {failed} failed today",
             "href": "/requests"},
        ]
        if night:
            st = night.stats or {}
            tiles.append({"label": "Last Night" if night.status != "running" else "Tonight",
                          "value": f"{st.get('saved', 0)} new",
                          "sub": f"{st.get('companies', 0)} enriched · {night.status}",
                          "href": "/settings/night" if can(user, "night") else "/requests"})
        else:
            tiles.append({"label": "Night Run", "value": "not yet", "sub": "runs at night when switched on",
                          "href": "/settings/night" if can(user, "night") else "/requests"})
        return render(request, s, user, "dashboard.html", active_nav="dashboard", help="dashboard",
                      tiles=tiles, attention=_attention(s, user, groups, stats), groups=groups, stats=stats,
                      activity=_activity(s, user, groups), inbox_new=inbox_new)


@router.get("/dashboard/jobs", response_class=HTMLResponse)
def running_jobs(request: Request):
    """The Running Jobs panel (reloads itself every few seconds)."""
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        base = [Job.deleted_at.is_(None), jobs_clause(user)]
        running = s.scalars(select(Job).where(Job.status.in_(list(control.RUNNING)), *base)
                            .order_by(Job.started_at.desc().nulls_last()).limit(6)).all()
        waiting_q = select(Job).where(Job.status.in_(list(control.WAITING)), *base)
        waiting_n = s.scalar(select(func.count()).select_from(waiting_q.subquery())) or 0
        waiting = s.scalars(waiting_q.order_by(Job.id).limit(5)).all()
        last = s.scalar(select(Job.finished_at).where(Job.finished_at.is_not(None), *base)
                        .order_by(Job.finished_at.desc()).limit(1))
        names = {g.id: g.name for g in view_groups(s, user)}
        users = dict(s.execute(select(User.id, User.username)).all())
        rows = []
        for j in running:
            st = j.stats or {}
            done, total = int(st.get("page_no") or 0), int(st.get("pages_total") or 0)
            pct = int(done * 100 / total) if total else (100 if j.status == "stopping" else 8)
            found = f"{st.get('saved', 0)} new" if j.kind != "enrich" else f"{st.get('fields', 0)} fields filled"
            rows.append({"j": j, "pct": min(100, pct), "found": found, "dir": names.get(j.group_id, ""),
                         "who": users.get(j.user_id, "NetGate"), "since": j.started_at or j.created_at,
                         "control": can_control(user, j)})
        return templates.TemplateResponse(request, "_runjobs.html", {
            "user": user, "rows": rows, "waiting": waiting, "waiting_n": waiting_n, "names": names, "last": last,
            "running_n": len(running), "req_groups": [g for g in view_groups(s, user) if can(user, "request", g.id)]})


def _check(name, fn):
    try:
        return name, fn()
    except Exception:   # noqa: BLE001 - any failure means "not reachable"
        return name, ("offline", "red")


def _ollama(url):
    r = httpx.get(url.rstrip("/") + "/api/tags", timeout=3)
    return ("online", "green") if r.status_code == 200 else ("not answering", "red")


def _searx(problems: int = 0):
    r = httpx.get(f"{crawl.SEARXNG_URL}/healthz", timeout=3)
    if r.status_code >= 500:
        return ("not answering", "red")
    if problems:
        return (f"online · {problems} engine{'s' if problems != 1 else ''} blocking", "amber")
    return ("online", "green")


@router.get("/dashboard/system", response_class=HTMLResponse)
def system_status(request: Request):
    """Loaded after the page (it waits up to 3 seconds for each service)."""
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        servers = s.scalars(select(AIServer).where(AIServer.enabled).order_by(AIServer.id)).all()
        conn = connections(s)
        checks = []
        for sv in servers[:3]:
            if sv.kind == "ollama":
                checks.append((f"AI server ({sv.name})", lambda u=sv.url: _ollama(u)))
            else:
                checks.append((f"AI server ({sv.name})",
                               lambda k=sv.api_key: ("set up", "green") if k else ("no API key", "amber")))
        if not servers:
            checks.append(("AI server", lambda: ("not set up", "amber")))
        checks.append(("Browser (renderer)", lambda: ("running", "green") if crawl.renderer_status() else ("offline", "red")))
        blocked = len(engines.problems(s))
        checks.append(("Search engine", lambda: _searx(blocked)))
        checks.append(("eBay API", lambda: ("set up", "green") if ebay.ready(conn) else ("not set up", "amber")))
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda c: _check(*c), checks))
    return templates.TemplateResponse(request, "_system.html", {"rows": rows})


# ---------- Directories page ----------

@router.get("/directories", response_class=HTMLResponse)
def directories_page(request: Request, sort: str = "menu", view: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        groups = view_groups(s, user)
        stats = dir_stats(s, groups, user)
        if view in ("grid", "list"):
            if (user.prefs or {}).get("dir_view") != view:
                user.prefs = {**(user.prefs or {}), "dir_view": view}
                s.commit()
        else:
            view = (user.prefs or {}).get("dir_view") or "grid"
        keyf = {"name": lambda g: g.name.lower(), "contacts": lambda g: -stats[g.id]["contacts"],
                "inbox": lambda g: -stats[g.id]["inbox"], "least": lambda g: stats[g.id]["pct"]}.get(sort)
        ordered = sorted(groups, key=keyf) if keyf else list(groups)
        tiles = {g.id: TILES[i % len(TILES)] for i, g in enumerate(groups)}
        total = s.scalar(select(func.count(Record.id)).where(visible_records_clause(user, groups))) or 0
        return render(request, s, user, "directories.html", active_nav="directories", help="directories",
                      groups=ordered, stats=stats, tiles=tiles, sort=sort, sorts=SORTS, view=view, total=total)
