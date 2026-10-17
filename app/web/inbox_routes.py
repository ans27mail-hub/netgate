"""The Inbox: new companies wait here until someone accepts them into a directory or rejects them."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from .. import contacts as C
from .. import control, learn, methods
from ..auth import can, own_contacts_only, sees_all_groups
from ..db import Group, InboxItem, Record, SessionLocal
from .common import back, current_user, flash, go, record_fields_map, render, require, view_groups
from .filters import Filters

router = APIRouter()
TABS = [("new", "New"), ("enriched", "Enriched"), ("rejected", "Rejected")]
LIMIT = 300


def _items_stmt(user, groups, tab: str):
    stmt = select(InboxItem, Record).join(Record, Record.id == InboxItem.record_id)
    if not sees_all_groups(user):
        stmt = stmt.where(InboxItem.group_id.in_([g.id for g in groups] or [-1]))
    if own_contacts_only(user):   # only companies they found first
        stmt = stmt.where(Record.found_by == user.id)
    if tab == "rejected":
        return stmt.where(InboxItem.status == "rejected")
    stmt = stmt.where(InboxItem.status == "new")
    return stmt.where(Record.enrich_runs > 0) if tab == "enriched" else stmt.where(Record.enrich_runs == 0)


@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, tab: str = "new"):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        tab = tab if tab in dict(TABS) else "new"
        groups = view_groups(s, user)
        flt = Filters(request, groups=groups)
        dirs = [int(d) for d in flt.values["dir"] if d.isdigit()]
        counts = {}
        for key, _ in TABS:
            st = _items_stmt(user, groups, key)
            counts[key] = s.scalar(select(func.count()).select_from(st.subquery()))
        stmt = _items_stmt(user, groups, tab)
        if dirs:
            stmt = stmt.where(InboxItem.group_id.in_(dirs))
            flt.values["dir"] = []          # handled here, not as a membership filter
        if flt.values["method"]:
            stmt = stmt.where(InboxItem.method.in_(flt.values["method"]))
            flt.values["method"] = []
        stmt = flt.apply(stmt)
        flt.values["dir"] = [str(d) for d in dirs]
        flt.values["method"] = [m for k, m in flt.raw if k == "method"]
        order = request.query_params.get("sort", "new")
        if order == "score":
            stmt = stmt.order_by(InboxItem.suggest.desc().nulls_last(), InboxItem.score.desc().nulls_last())
        elif order == "name":
            stmt = stmt.order_by(Record.title)
        else:
            stmt = stmt.order_by(InboxItem.created_at.desc())
        rows = s.execute(stmt.limit(LIMIT)).all()
        by_id = {g.id: g for g in groups}
        # keyword rows: per directory and method, like "eBay search: … → for Online retailers"
        kw_rows = []
        for g in groups:
            if not g.keywords or not can(user, "keywords", g.id):
                continue
            for m in methods.enabled_find_methods(g):
                kws = [k for k in g.keywords if (k.method or "all") in ("all", m)]
                if kws:
                    kw_rows.append({"method": m, "group": g, "keywords": kws})
        fmap = record_fields_map(s, [r for _, r in rows])
        base = _items_stmt(user, groups, tab)
        options = {k: sorted({str(v) for v in s.scalars(base.with_only_columns(Record.data[k].astext).distinct()
                                                         .limit(2000)).all() if v}, key=str.lower)[:300]
                   for k in ("country", "city")}
        return render(request, s, user, "inbox.html", active_nav="inbox", help="inbox", tab=tab, tabs=TABS,
                      counts=counts, rows=rows, by_id=by_id, flt=flt, kw_rows=kw_rows, fmap=fmap, sort=order,
                      targets=[g for g in groups if can(user, "review", g.id)], options=options,
                      limited=len(rows) >= LIMIT, q=flt.q)


async def _selected(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    return form, ids


def _rescore(gids):
    for gid in set(gids):
        try:
            control.queue().enqueue(learn.rescore_group, gid, job_timeout=600)
        except Exception:
            pass


@router.post("/inbox/accept")
async def accept(request: Request):
    form, ids = await _selected(request)
    into = int(form.get("group_id") or 0) or None
    with SessionLocal() as s:
        user = current_user(s, request)
        n, gids, missing_dir = 0, [], 0
        for item in s.scalars(select(InboxItem).where(InboxItem.id.in_(ids or [-1]))).all():
            target = into or item.group_id
            if not target:
                missing_dir += 1
                continue
            if item.status == "accepted" or not can(user, "review", target):
                continue
            if C.accept(s, item, user, into):
                n += 1
                gids.append(target)
        s.commit()
        g = s.get(Group, into) if into else None
        msg = f"{n} accepted" + (f" into {g.name}" if g else "") + "."
        if missing_dir:
            msg += f" {missing_dir} had no directory yet: choose one in “Accept into”."
        flash(request, msg if ids else "Tick one or more companies first.", not ids or (missing_dir and not n))
    _rescore(gids)
    return back(request, "/inbox")


@router.post("/inbox/reject")
async def reject(request: Request):
    form, ids = await _selected(request)
    reason = str(form.get("reason") or form.get("reason_text") or "").strip()[:200]
    with SessionLocal() as s:
        user = current_user(s, request)
        n, gids = 0, []
        for item in s.scalars(select(InboxItem).where(InboxItem.id.in_(ids or [-1]))).all():
            if item.status != "new" or not can(user, "review", item.group_id):
                continue
            C.reject(s, item, user, reason)
            n += 1
            gids.append(item.group_id)
        s.commit()
        flash(request, (f"{n} rejected" + (f" ({reason})" if reason else "") + ". They are in the Rejected tab "
                        "and can be restored.") if ids else "Tick one or more companies first.", not ids)
    _rescore(gids)
    return back(request, "/inbox")


@router.post("/inbox/restore")
async def restore(request: Request):
    form, ids = await _selected(request)
    with SessionLocal() as s:
        user = current_user(s, request)
        n, gids = 0, []
        for item in s.scalars(select(InboxItem).where(InboxItem.id.in_(ids or [-1]))).all():
            if item.status != "rejected" or not can(user, "review", item.group_id):
                continue
            C.restore(s, item, user)
            n += 1
            gids.append(item.group_id)
        s.commit()
        flash(request, f"{n} restored to the Inbox.")
    _rescore(gids)
    return back(request, "/inbox?tab=rejected")


@router.post("/inbox/enrich")
async def enrich(request: Request):
    from .contacts_routes import enrich_many
    form, ids = await _selected(request)
    with SessionLocal() as s:
        user = current_user(s, request)
        rids = s.scalars(select(InboxItem.record_id).where(InboxItem.id.in_(ids or [-1]))).all()
        n = enrich_many(s, user, list(dict.fromkeys(rids)))
        flash(request, f"Enrich started for {n} compan{'y' if n == 1 else 'ies'}. They move to the Enriched tab "
                       "when done." if n else "Tick one or more companies first.", not n)
    return back(request, "/inbox")


@router.post("/inbox/rescore")
def rescore(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "review")
        gids = s.scalars(select(InboxItem.group_id).where(InboxItem.status == "new").distinct()).all()
        for gid in gids:
            learn.rescore_group(gid)
        flash(request, "AI suggestions refreshed from your latest decisions.")
    return go("/inbox")
