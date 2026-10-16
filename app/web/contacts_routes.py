"""All contacts, a directory's page, the contact card, export, saved views."""
import csv
import io

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from .. import contacts as C
from ..auth import can
from ..db import Group, InboxItem, Membership, Record, SessionLocal, slugify
from ..jobs import night_settings
from .common import (SPECIAL_COLS, Forbidden, all_groups, back, current_user, display_for, flash, fmt_value, go,
                     last_night, memberships_map, record_fields_map, render, require, start_job, templates,
                     view_groups, visible_records_clause)
from .filters import Filters, distinct_values

router = APIRouter()
LIMIT = 500


def _sort(records, sort, fmap, fields):
    from ..jobs import empty
    if sort == "name":
        records.sort(key=lambda r: (r.title or "").lower())
    elif sort == "least":
        records.sort(key=lambda r: fmap.get(r.id, ([], 0, 0))[1])
    elif sort == "added":
        records.sort(key=lambda r: r.created_at or r.updated_at, reverse=True)
    elif sort.startswith("f_"):
        field = next((f for f in fields if f.key == sort[2:] and f.sort), None)
        if field:
            choices = field.choice_list()

            def key(r):
                v = (r.data or {}).get(field.key)
                if isinstance(v, list):
                    v = v[0] if v else None
                if empty(v):
                    return (1, 0.0, "")
                if field.type == "choice":
                    return (0, float(choices.index(v)) if v in choices else float(len(choices)), "")
                if field.type == "number":
                    try:
                        return (0, -float(str(v).rstrip("%")), "")
                    except ValueError:
                        return (1, 0.0, "")
                if str(v).rstrip("%").replace(".", "", 1).isdigit():
                    return (0, -float(str(v).rstrip("%")), "")
                return (0, 0.0, str(v).lower())
            records.sort(key=key)
    return records


def _columns(user, key: str, fields: list) -> list[str]:
    saved = ((user.prefs or {}).get("cols") or {}).get(key)
    keys = {f.key for f in fields} | set(SPECIAL_COLS)
    if saved:
        return [c for c in saved if c in keys]
    if key == "all":
        return [k for k in ("city", "country", "contact_email", "website") if k in {f.key for f in fields}] \
            + ["_dirs", "_complete"]
    return [f.key for f in fields if f.list] + ["_complete", "_updated"]


def _all_fields(s) -> list:
    out, seen = [], set()
    for g in all_groups(s):
        for f in g.fields:
            if f.key not in seen:
                seen.add(f.key)
                out.append(f)
    return out


def _listing(request: Request, s, user, sel=None):
    groups = view_groups(s, user)
    fields = list(sel.fields) if sel else _all_fields(s)
    flt = Filters(request, fields=fields if sel else [f for f in fields if f.filter], groups=groups)
    if sel:
        base = select(Record).where(Record.id.in_(select(Membership.record_id).where(Membership.group_id == sel.id)))
    else:
        base = select(Record).where(visible_records_clause(user, groups))
    email_keys = tuple({f.key for f in fields if f.type == "email"} | {"contact_email", "email"})
    phone_keys = tuple({f.key for f in fields if f.type == "phone"} | {"phone", "whatsapp"})
    stmt = flt.apply(base, email_keys, phone_keys)
    records = s.scalars(stmt.order_by(Record.updated_at.desc()).limit(LIMIT)).all()
    fmap = record_fields_map(s, records, sel)
    records = flt.keep_complete(list(records), fmap)
    sort = request.query_params.get("sort", "updated")
    records = _sort(records, sort, fmap, fields)
    d = display_for(s, user)
    view = request.query_params.get("view", "")
    if view in ("grid", "list") and (user.prefs or {}).get("view") != view:
        user.prefs = {**(user.prefs or {}), "view": view}   # remember the last view per user
        s.commit()
    view = view if view in ("grid", "list") else ((user.prefs or {}).get("view") or d["view"])
    stats = None
    if sel:
        all_recs = s.scalars(base).all()
        full = record_fields_map(s, all_recs, sel)
        done = sum(1 for _, f, t in full.values() if f >= t)
        miss: dict = {}
        for r in all_recs:
            for f in sel.fields:
                if C.empty((r.data or {}).get(f.key)):
                    miss[f.name] = miss.get(f.name, 0) + 1
        top_missing = [n for n, _ in sorted(miss.items(), key=lambda kv: -kv[1])[:2]]
        stats = {"total": len(all_recs), "complete": done, "pct": int(done * 100 / len(all_recs)) if all_recs else 0,
                 "missing": top_missing}
    options = {"country": distinct_values(s, "country", base), "city": distinct_values(s, "city", base)}
    for f in flt.fields.values():
        if f.type == "choice":
            options[f.key] = f.choice_list() + ["Unknown"]
        elif f.type == "list":
            vals = set()
            for v in s.scalars(base.with_only_columns(Record.data[f.key]).limit(3000)).all():
                for item in (v if isinstance(v, list) else [v]):
                    if item not in (None, ""):
                        vals.add(str(item))
            options[f.key] = sorted(vals, key=str.lower)[:300]
        else:
            options[f.key] = distinct_values(s, f.key, base)
    col_key = str(sel.id) if sel else "all"
    return dict(sel_group=sel, records=records, fmap=fmap, flt=flt, sort=sort, view=view, stats=stats,
                fields=fields, options=options, cols=_columns(user, col_key, fields), col_key=col_key,
                dirs_of=memberships_map(s, records), q=flt.q, limited=len(records) >= LIMIT,
                colfields={f.key: f for f in fields}, groups=groups, night=last_night(s), night_cfg=night_settings(s),
                edit_gids=[g.id for g in groups if can(user, "edit", g.id)])


@router.get("/contacts", response_class=HTMLResponse)
def all_contacts(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        ctx = _listing(request, s, user)
        return render(request, s, user, "contacts.html", active_nav="contacts", help="contacts", **ctx)


@router.get("/d/{gid}", response_class=HTMLResponse)
def directory_page(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        sel = s.get(Group, gid)
        if not sel:
            return go("/contacts")
        require(user, "view", gid)
        ctx = _listing(request, s, user, sel)
        counts = dict(s.execute(select(Membership.group_id, func.count(Membership.record_id))
                                .group_by(Membership.group_id)).all())
        return render(request, s, user, "contacts.html", active_nav=f"d{gid}", help="directories",
                      switch_counts=counts, **ctx)


# ---------- the contact card ----------

def _card(request, s, user, rec, edit=False, ctx_gid=None):
    groups = all_groups(s)
    by_id = {g.id: g for g in groups}
    mids = C.member_ids(s, rec.id)
    items = s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id).order_by(InboxItem.id)).all()
    fields = C.fields_for(s, rec)
    filled, total = C.completeness_of(rec, fields)
    return templates.TemplateResponse(request, "_bigcard.html", {
        "r": rec, "user": user, "fields": fields, "filled": filled, "total": total,
        "members": [by_id[g] for g in mids if g in by_id], "items": items, "by_id": by_id, "edit": edit,
        "ctx_gid": ctx_gid if ctx_gid in mids else None,
        "edit_ids": [g for g in mids if can(user, "edit", g)],
        "add_targets": [g for g in groups if g.id not in mids and can(user, "edit", g.id)]})


@router.get("/records/{rid}/open", response_class=HTMLResponse)
def open_card(request: Request, rid: int, edit: int = 0, from_: int | None = Query(None, alias="from")):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec):
            raise Forbidden
        if edit and not can(user, "edit"):
            raise Forbidden
        return _card(request, s, user, rec, bool(edit), from_)


@router.post("/records/{rid}/edit", response_class=HTMLResponse)
async def edit_record(request: Request, rid: int, from_: int | None = Query(None, alias="from")):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec):
            raise Forbidden
        require(user, "edit")
        from ..jobs import clean
        data, src = dict(rec.data or {}), dict(rec.sources or {})
        for f in C.fields_for(s, rec):
            if f"f_{f.key}" not in form:
                continue
            raw = str(form.get(f"f_{f.key}") or "").strip()
            v = clean(f, raw) if raw else None
            if C.empty(v):
                if data.get(f.key) not in (None, "", []):
                    data.pop(f.key, None)
                    src.pop(f.key, None)
            elif v != data.get(f.key):
                data[f.key], src[f.key] = v, f"edited by {user.username}"
        name = str(form.get("title") or "").strip()
        if name and name != rec.title:
            from ..db import name_key
            rec.title, rec.name_key = name[:300], name_key(name)
        rec.summary = str(form.get("summary") or "").strip()[:1000]
        rec.notes = str(form.get("notes") or "").strip()[:2000]
        from ..db import url_domain
        rec.data, rec.sources = data, src
        rec.domain = url_domain(data.get("website")) or rec.domain
        C.add_history(rec, f"Edited by {user.username}")
        s.commit()
        return _card(request, s, user, rec, ctx_gid=from_)


@router.post("/records/{rid}/directories")
def record_directory(request: Request, rid: int, group_id: int = Form(...), action: str = Form("add"),
                     from_id: int = Form(0)):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec):
            raise Forbidden
        require(user, "edit", group_id)
        g = s.get(Group, group_id)
        gname = g.name if g else "the directory"
        if action == "remove":
            C.remove_from_directory(s, rec, group_id, user)
            flash(request, f"{rec.title} removed from {gname}. The contact itself is kept.")
        elif action == "move":
            require(user, "edit", from_id)
            src = s.get(Group, from_id)
            if C.move(s, rec, [from_id], group_id, user):
                flash(request, f"{rec.title} moved from {src.name if src else 'its directory'} to {gname}. "
                               "All its details and history are kept." + _extra_note(s, [from_id], g))
        elif C.add_to_directory(s, rec, group_id, user):
            flash(request, f"{rec.title} added to {gname}.")
        s.commit()
    return back(request, "/contacts")


def _extra_note(s, from_ids, target) -> str:
    """Fields the target directory has that the old ones didn't: they now show as Missing."""
    if not target:
        return ""
    had = {f.key for gid in from_ids if (g := s.get(Group, gid)) for f in g.fields}
    extra = [f.name for f in target.fields if f.key not in had]
    if not extra:
        return ""
    names = ", ".join(extra[:4]) + ("…" if len(extra) > 4 else "")
    return f" {target.name} has {len(extra)} field{'s' if len(extra) != 1 else ''} they didn't have before ({names}): " \
           "empty ones show as Missing until Enrich fills them."


@router.post("/records/move")
async def move_selected(request: Request):
    """Move the ticked contacts to another directory (out of one directory, or out of all their directories)."""
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    gid = int(form.get("group_id") or 0)
    from_raw = str(form.get("from_id") or "")
    from_id = int(from_raw) if from_raw.isdigit() else 0
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "edit", gid)
        if from_id:
            require(user, "edit", from_id)
        target = s.get(Group, gid)
        if not target:
            return back(request, "/contacts")
        if not ids:
            flash(request, "Tick one or more contacts first.", True)
            return back(request, "/contacts")
        n = skipped = 0
        sources: set = set()
        for rid in ids:
            rec = s.get(Record, rid)
            if not rec or not C.can_see_record(s, user, rec):
                continue
            mids = C.member_ids(s, rec.id)
            src = [from_id] if from_id else [m for m in mids if m != gid and can(user, "edit", m)]
            if not src or not any(m in mids for m in src):
                if not mids and C.add_to_directory(s, rec, gid, user):   # in no directory at all: just add it
                    n += 1
                else:
                    skipped += 1
                continue
            if C.move(s, rec, src, gid, user):
                n += 1
                sources.update(src)
            else:
                skipped += 1
        s.commit()
        msg = f"{n} contact{'s' if n != 1 else ''} moved to {target.name}. All details and history are kept."
        if skipped:
            msg += f" {skipped} skipped (already only in {target.name}, or not in the chosen directory)."
        flash(request, msg + (_extra_note(s, list(sources), target) if n else ""), not n)
    return back(request, "/contacts")


@router.post("/records/add-to-directory")
async def add_selected_to_directory(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    gid = int(form.get("group_id") or 0)
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "edit", gid)
        n = 0
        for rid in ids:
            rec = s.get(Record, rid)
            if rec and C.can_see_record(s, user, rec) and C.add_to_directory(s, rec, gid, user):
                n += 1
        s.commit()
        g = s.get(Group, gid)
        flash(request, f"{n} contact{'s' if n != 1 else ''} added to {g.name if g else 'the directory'}." if ids
              else "Tick one or more contacts first.", not ids)
    return back(request, "/contacts")


def enrich_many(s, user, ids: list[int], steps=None) -> int:
    n = 0
    for rid in ids:
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec):
            continue
        gids = C.member_ids(s, rec.id) + C.open_item_group_ids(s, rec.id)
        if not can(user, "enrich", gids[0] if gids else None):
            continue
        start_job(s, user, "enrich", rec.title, gids[0] if gids else None, record_id=rec.id,
                  params={"steps": steps} if steps else {})
        n += 1
    return n


@router.post("/records/{rid}/enrich")
def enrich_one(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        if not enrich_many(s, user, [rid]):
            raise Forbidden
        flash(request, "Enrich started. The card updates when it finishes — see AI activity.")
    return back(request)


@router.post("/records/enrich-selected")
async def enrich_selected(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:100]
    with SessionLocal() as s:
        user = current_user(s, request)
        n = enrich_many(s, user, ids)
        flash(request, f"Enrich started for {n} contact{'' if n == 1 else 's'}." if n else
              "Tick one or more contacts first.", not n)
    return back(request)


@router.post("/groups/{gid}/enrich-incomplete")
def enrich_incomplete(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "enrich", gid)
        group = s.get(Group, gid)
        recs = s.scalars(select(Record).where(Record.id.in_(select(Membership.record_id)
                                                            .where(Membership.group_id == gid)))).all()
        todo = sorted((C.completeness_of(r, group.fields)[0], r.id) for r in recs
                      if C.completeness_of(r, group.fields)[0] < len(group.fields))
        n = enrich_many(s, user, [rid for _, rid in todo[:50]])
        flash(request, f"Enrich started for {n} incomplete contact{'' if n == 1 else 's'}"
                       + (" (the 50 least complete; the rest can run tonight)." if len(todo) > 50 else "."))
    return go(f"/d/{gid}")


@router.post("/records/{rid}/delete")
def delete_record(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec:
            return go("/contacts")
        gids = C.member_ids(s, rec.id) + C.open_item_group_ids(s, rec.id)
        if not all(can(user, "delete", g) for g in gids) or not can(user, "delete"):
            raise Forbidden
        s.delete(rec)
        s.commit()
        flash(request, f"{rec.title} deleted.")
    return back(request, "/contacts")


# ---------- preferences & saved views ----------

@router.post("/prefs/columns")
async def pref_columns(request: Request):
    form = await request.form()
    key = str(form.get("col_key", ""))
    with SessionLocal() as s:
        user = current_user(s, request)
        cols = dict((user.prefs or {}).get("cols") or {})
        if form.get("reset"):
            cols.pop(key, None)
        else:
            cols[key] = [c for c in form.getlist("cols") if c]
        user.prefs = {**(user.prefs or {}), "cols": cols}
        s.commit()
    return back(request)


@router.post("/views")
def save_view(request: Request, name: str = Form(...), path: str = Form(...), qs: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        name = name.strip()[:60]
        if not name or not (path == "/contacts" or path.startswith("/d/") or path == "/inbox"):
            flash(request, "Give the view a name.", True)
            return back(request)
        views = [v for v in ((user.prefs or {}).get("views") or []) if v.get("name") != name]
        views.append({"name": name, "path": path, "qs": qs})
        user.prefs = {**(user.prefs or {}), "views": views[-20:]}
        s.commit()
        flash(request, f"View “{name}” saved. It's in the menu on the left.")
    return back(request)


@router.post("/views/delete")
def delete_view(request: Request, name: str = Form(...)):
    with SessionLocal() as s:
        user = current_user(s, request)
        user.prefs = {**(user.prefs or {}), "views": [v for v in ((user.prefs or {}).get("views") or [])
                                                       if v.get("name") != name]}
        s.commit()
    return back(request)


# ---------- export ----------

@router.get("/export.csv")
def export_csv(request: Request, group: int | None = None):
    with SessionLocal() as s:
        user = current_user(s, request)
        sel = s.get(Group, group) if group else None
        require(user, "export", sel.id if sel else None)
        ctx = _listing(request, s, user, sel)
        fields = ctx["fields"] if sel else [f for f in ctx["fields"]]
        dirs_of = ctx["dirs_of"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Company", "Directories"] + [f.name for f in fields] + [
            "Description", "Facebook", "Instagram", "LinkedIn", "Store pages", "Notes", "First found on", "Updated"])
        for r in ctx["records"]:
            w.writerow([r.title, "; ".join(dirs_of.get(r.id, []))] + [fmt_value(r, f) if fmt_value(r, f) != "—" else ""
                                                                    for f in fields]
                       + [r.summary, (r.social or {}).get("facebook", ""), (r.social or {}).get("instagram", ""),
                          (r.social or {}).get("linkedin", ""), " ".join((r.links or {}).values()), r.notes or "",
                          r.source_url, r.updated_at.strftime("%Y-%m-%d") if r.updated_at else ""])
    fname = f"netgate-{slugify(sel.name) if sel else 'contacts'}.csv"
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
