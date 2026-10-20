"""All contacts, a directory's page, the contact card, export, saved views."""
import csv
import io

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from .. import contacts as C
from .. import crawl, ebay, methods, pages
from .. import tags as T
from ..auth import can, own_contacts_only, sees_all_groups, sees_methods
from ..db import ExistingHit, Group, InboxItem, Membership, PageRead, Record, SessionLocal, User, slugify
from ..jobs import night_settings
from .common import (SPECIAL_COLS, Forbidden, all_groups, back, card_cfg, card_fields, current_user, display_for,
                     flash, fmt_value, go, last_night, memberships_map, own_clause, record_fields_map, render,
                     require, start_job, templates, view_groups, visible_records_clause)
from .filters import Filters, distinct_values

router = APIRouter()
LIMIT = 500


def _sort(records, sort, fmap, fields, tmap=None):
    from ..jobs import empty
    if sort == "tag":
        records.sort(key=lambda r: T.tag_order_key(tmap or {}, r.id))
    elif sort == "name":
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
    tags = T.all_tags(s)
    flt = Filters(request, fields=fields if sel else [f for f in fields if f.filter], groups=groups, tags=tags)
    if sel:
        base = select(Record).where(Record.id.in_(select(Membership.record_id).where(Membership.group_id == sel.id)),
                                    own_clause(user))
    else:
        base = select(Record).where(visible_records_clause(user, groups))
    email_keys = tuple({f.key for f in fields if f.type == "email"} | {"contact_email", "email"})
    phone_keys = tuple({f.key for f in fields if f.type == "phone"} | {"phone", "whatsapp"})
    stmt = flt.apply(base, email_keys, phone_keys)
    records = s.scalars(stmt.order_by(Record.updated_at.desc()).limit(LIMIT)).all()
    fmap = record_fields_map(s, records, sel)
    records = flt.keep_complete(list(records), fmap)
    tmap = T.tags_map(s, [r.id for r in records])
    sort = request.query_params.get("sort", "updated")
    records = _sort(records, sort, fmap, fields, tmap)
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
                colfields={f.key: f for f in fields}, groups=groups, enrich_steps=enrich_step_choices(s),
                enrich_choice=enrich_choice(user), night=last_night(s), night_cfg=night_settings(s),
                edit_gids=[g.id for g in groups if can(user, "edit", g.id)], tags=tags, tmap=tmap,
                tag_labels={t.id: t.name for t in tags},
                tag_counts=T.counts(s, base.with_only_columns(Record.id)), card=card_cfg(s, user, sel),
                cardf=card_fields(user, sel), tint=T.tint)


@router.get("/contacts", response_class=HTMLResponse)
def all_contacts(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "view")
        ctx = _listing(request, s, user)
        return render(request, s, user, "contacts.html", active_nav="contacts", help="contacts", **ctx)


def _hits_stmt(user, gid):
    stmt = select(ExistingHit).where(ExistingHit.group_id == gid)
    if own_contacts_only(user) or not sees_all_groups(user) and not can(user, "review", gid):
        stmt = stmt.where(ExistingHit.user_id == user.id)
    return stmt


@router.get("/d/{gid}", response_class=HTMLResponse)
def directory_page(request: Request, gid: int, tab: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        sel = s.get(Group, gid)
        if not sel:
            return go("/contacts")
        require(user, "view", gid)
        if sel.is_test:
            require(user, "testing")
        ctx = _listing(request, s, user, sel)
        mq = select(Membership.group_id, func.count(Membership.record_id)).group_by(Membership.group_id)
        if own_contacts_only(user):
            mq = mq.join(Record, Record.id == Membership.record_id).where(Record.found_by == user.id)
        counts = dict(s.execute(mq).all())
        hits_n = s.scalar(select(func.count()).select_from(_hits_stmt(user, gid).subquery())) or 0
        hits = []
        if tab == "existing":
            rows = s.scalars(_hits_stmt(user, gid).order_by(ExistingHit.at.desc()).limit(500)).all()
            recs = {r.id: r for r in s.scalars(select(Record).where(Record.id.in_([h.record_id for h in rows]))).all()}
            names = dict(s.execute(select(User.id, User.username)).all())
            for h in rows:
                r = recs.get(h.record_id)
                if r:
                    hits.append({"hit": h, "r": r, "by": names.get(h.user_id, "(deleted user)"),
                                 "first": names.get(r.found_by, "(deleted user)") if r.found_by else "NetGate",
                                 "limited": C.limited_view(user, r), "enrich": C.may_enrich(user, r, gid)})
        return render(request, s, user, "contacts.html", active_nav=f"d{gid}", help="directories",
                      switch_counts=counts, dtab="existing" if tab == "existing" else "", hits=hits, hits_n=hits_n,
                      **ctx)


# ---------- the contact card ----------

def _show(v) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def move_preview(s, records: list, target, from_ids: list | None) -> dict:
    """v1.0: what changes when these contacts move to `target`: details kept but hidden (fields the target
    doesn't have), and the target's fields they are missing."""
    hidden: dict = {}
    missing: dict = {}
    for rec in records:
        gids = from_ids or [g for g in C.member_ids(s, rec.id) if g != target.id]
        src_fields = {f.key: f.name for gid in gids if (g := s.get(Group, gid)) for f in g.fields}
        tkeys = {f.key for f in target.fields}
        for k, name in src_fields.items():
            if k not in tkeys and not C.empty((rec.data or {}).get(k)):
                hidden[name] = hidden.get(name, 0) + 1
        for f in target.fields:
            if C.empty((rec.data or {}).get(f.key)):
                missing[f.name] = missing.get(f.name, 0) + 1
    return {"hidden": hidden, "missing": missing, "n": len(records)}


@router.get("/records/{rid}/move-preview", response_class=HTMLResponse)
def move_preview_one(request: Request, rid: int, group_id: int = 0, from_id: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec, target = s.get(Record, rid), s.get(Group, group_id)
        if not rec or not target or not C.can_see_record(s, user, rec):
            return HTMLResponse("")
        p = move_preview(s, [rec], target, [from_id] if from_id else None)
        return templates.TemplateResponse(request, "_movepreview.html", {"p": p, "target": target, "user": user,
                                                                           "may_enrich": C.may_enrich(user, rec, target.id)})


@router.get("/records/move-preview", response_class=HTMLResponse)
def move_preview_many(request: Request, group_id: int = 0, from_id: str = ""):
    ids = [int(i) for i in request.query_params.getlist("ids") if str(i).isdigit()][:500]
    with SessionLocal() as s:
        user = current_user(s, request)
        target = s.get(Group, group_id)
        recs = [r for r in s.scalars(select(Record).where(Record.id.in_(ids or [-1]))).all()
                if C.can_see_record(s, user, r)]
        if not target or not recs:
            return HTMLResponse("")
        p = move_preview(s, recs, target, [int(from_id)] if from_id.isdigit() else None)
        return templates.TemplateResponse(request, "_movepreview.html", {"p": p, "target": target, "user": user,
                                                                           "may_enrich": can(user, "enrich", target.id)})


def _card(request, s, user, rec, edit=False, ctx_gid=None, notice=""):
    groups = all_groups(s)
    by_id = {g.id: g for g in groups}
    mids = C.member_ids(s, rec.id)
    items = s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id).order_by(InboxItem.id)).all()
    fields = C.fields_for(s, rec)
    filled, total = C.completeness_of(rec, fields)
    limited = C.limited_view(user, rec)
    if limited and (user.existing_view or "full") == "fields":
        allowed = set(user.existing_fields or [])
        fields = [f for f in fields if f.key in allowed]
    ctx_gid = ctx_gid if ctx_gid in mids else None
    panel_group = by_id.get(ctx_gid) or (by_id.get(mids[0]) if mids else None)
    rec_tags = T.tags_map(s, [rec.id]).get(rec.id, [])
    can_tag = not limited and any(can(user, "edit", g) for g in mids) if mids else (not limited and can(user, "edit"))
    finder = s.get(User, rec.found_by) if rec.found_by else None
    shown = {f.key for f in fields}
    names = {f.key: f.name for g in groups for f in g.fields}
    other_details = [{"key": k, "name": names.get(k, k.replace("_", " ").capitalize()), "value": _show(v)}
                     for k, v in (rec.data or {}).items()
                     if k not in shown and not C.empty(v) and not k.startswith("_")] if not limited else []
    read_rows = []
    if not limited:
        read_rows = list(pages.for_record(s, rec.id, 40))
        if rec.source_url:
            read_rows += s.scalars(select(PageRead).where(PageRead.url == pages.norm(rec.source_url),
                                                          PageRead.record_id.is_(None)).order_by(PageRead.id.desc())
                                   .limit(3)).all()
    return templates.TemplateResponse(request, "_bigcard.html", {
        "enrich_steps": enrich_step_choices(s, rec), "enrich_choice": enrich_choice(user), "other_details": other_details,
        "read_rows": read_rows, "page_summary": pages.summary, "PURPOSES": pages.PURPOSES,
        "r": rec, "user": user, "fields": fields, "filled": filled, "total": total,
        "members": [by_id[g] for g in mids if g in by_id], "items": items, "by_id": by_id,
        "edit": edit and not limited, "ctx_gid": ctx_gid, "limited": limited,
        "show_all": not limited or (user.existing_view or "full") == "full",
        "edit_ids": [] if limited else [g for g in mids if can(user, "edit", g)],
        "add_targets": [] if limited else [g for g in groups if g.id not in mids and can(user, "edit", g.id)],
        "rec_tags": rec_tags, "can_tag": can_tag,
        "tag_choices": [t for t in T.all_tags(s) if T.usable_in(t, mids)],
        "may_enrich": C.may_enrich(user, rec, mids[0] if mids else None),
        "finder": finder.username if finder else ("(deleted user)" if rec.found_by else ""),
        "panel_group": panel_group, "panel_keys": [f.key for f in card_fields(user, panel_group)],
        "panel_mine": panel_group is not None and str(panel_group.id) in ((user.prefs or {}).get("cardfields") or {}),
        "can_dir_cards": panel_group is not None and can(user, "manage_dirs"), "notice": notice})


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
        if not rec or not C.can_see_record(s, user, rec) or C.limited_view(user, rec):
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
                C.stamp(rec, [f.key])
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
                     from_id: int = Form(0), enrich_now: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec) or C.limited_view(user, rec):
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
        if enrich_now and action in ("move", "add") and enrich_many(s, user, [rid]):
            request.session["flash"][0] += " Enrich is looking for the missing fields now."
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
            if not rec or not C.can_see_record(s, user, rec) or C.limited_view(user, rec):
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
        if form.get("enrich_now") and n:
            e = enrich_many(s, user, ids)
            msg += f" Enrich started for {e} of them to fill the missing fields."
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
            if rec and C.can_see_record(s, user, rec) and not C.limited_view(user, rec) \
                    and C.add_to_directory(s, rec, gid, user):
                n += 1
        s.commit()
        g = s.get(Group, gid)
        flash(request, f"{n} contact{'s' if n != 1 else ''} added to {g.name if g else 'the directory'}." if ids
              else "Tick one or more contacts first.", not ids)
    return back(request, "/contacts")


# ---------- Enrich Now ▾ (v0.9): choose the steps ----------

def enrich_step_choices(s, rec=None) -> list[dict]:
    """The Enrich steps with a reason when one can't work (for one contact, or for many when rec is None)."""
    conn = methods.connections(s)
    data = (rec.data or {}) if rec else {}
    social = (rec.social or {}) if rec else {}
    seller = rec and ((rec.ext or {}).get("ebay") or C.marketplace_id("ebay", (rec.links or {}).get("ebay", "")))
    out = []
    for key, label, desc, _ in methods.ENRICH_STEPS:
        why = ""
        if key == "ebay":
            if not ebay.ready(conn):
                why = "eBay keys are not set up (Settings → Connections)"
            elif rec is not None and not seller:
                why = "No eBay seller known for this contact"
        elif key == "find_site" and rec is not None and data.get("website"):
            why = "Its website is already known"
        elif key == "social" and rec is not None and all(social.get(k) for k in crawl.SOCIAL):
            why = "Facebook, Instagram and LinkedIn are already known"
        hint = "No website known yet: runs if Find Own Website finds one" \
            if key == "website" and rec is not None and not data.get("website") else ""
        out.append({"key": key, "label": label, "desc": desc, "why": why, "hint": hint})
    return out


def enrich_choice(user) -> dict:
    c = (user.prefs or {}).get("enrich_choice") or {}
    return {"steps": [k for k in (c.get("steps") or methods.ENRICH_STEP_KEYS) if k in methods.ENRICH_STEP_KEYS],
            "mode": "all" if c.get("mode") == "all" else "missing"}


def _choice_from_form(s, user, form) -> dict:
    """Steps / Only missing or Check all again / extra words from the Enrich Now ▾ menu (remembered per person).
    People who don't see search methods always use the directory's own Enrich steps."""
    if form.get("choose") != "1" or not sees_methods(user):
        return {}
    steps = [k for k in form.getlist("steps") if k in methods.ENRICH_STEP_KEYS]
    mode = "all" if form.get("mode") == "all" else "missing"
    user.prefs = {**(user.prefs or {}), "enrich_choice": {"steps": steps, "mode": mode}}
    params = {"steps": steps or None, "refresh": mode == "all"}
    words = str(form.get("words") or "").strip()[:300]
    if words:
        params["words"] = words
    return {k: v for k, v in params.items() if v}


def enrich_many(s, user, ids: list[int], steps=None, params: dict | None = None) -> int:
    n = 0
    params = dict(params or {})
    if steps:
        params["steps"] = steps
    for rid in ids:
        rec = s.get(Record, rid)
        if not rec or not C.can_see_record(s, user, rec):
            continue
        gids = C.member_ids(s, rec.id) + C.open_item_group_ids(s, rec.id)
        if not C.may_enrich(user, rec, gids[0] if gids else None):
            continue
        start_job(s, user, "enrich", rec.title, gids[0] if gids else None, record_id=rec.id, params=dict(params))
        n += 1
    return n


@router.post("/records/{rid}/enrich")
async def enrich_one(request: Request, rid: int):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        params = _choice_from_form(s, user, form)
        if form.get("choose") == "1" and sees_methods(user) and not params.get("steps"):
            flash(request, "Tick at least one Enrich step.", True)
            return back(request)
        if not enrich_many(s, user, [rid], params=params):
            raise Forbidden
        flash(request, "Enrich started" + (" (checking every field again)" if params.get("refresh") else "")
              + ". The card updates when it finishes — see AI activity.")
    return back(request)


@router.post("/records/enrich-selected")
async def enrich_selected(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:100]
    with SessionLocal() as s:
        user = current_user(s, request)
        n = enrich_many(s, user, ids, params=_choice_from_form(s, user, form))
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
        if not all(can(user, "delete", g) for g in gids) or not can(user, "delete") or C.limited_view(user, rec):
            raise Forbidden
        s.delete(rec)
        s.commit()
        flash(request, f"{rec.title} deleted.")
    return back(request, "/contacts")


# ---------- tags ----------

def _taggable(s, user, rec) -> bool:
    if not rec or not C.can_see_record(s, user, rec) or C.limited_view(user, rec):
        return False
    mids = C.member_ids(s, rec.id)
    return any(can(user, "edit", g) for g in mids) if mids else can(user, "edit")


@router.post("/records/{rid}/tags", response_class=HTMLResponse)
async def record_tags(request: Request, rid: int):
    """Set the tags of one contact (ticked boxes), or remove one (×). Answers with the updated card."""
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        if not _taggable(s, user, rec):
            raise Forbidden
        if form.get("remove"):
            T.remove_tag(s, rec, int(form.get("remove") or 0), user)
        else:
            T.set_tags(s, rec, {int(i) for i in form.getlist("tag_ids") if str(i).isdigit()}, user)
        s.commit()
        from_raw = str(form.get("from") or "")
        return _card(request, s, user, rec, ctx_gid=int(from_raw) if from_raw.isdigit() else None)


@router.post("/records/tags-bulk")
async def tags_bulk(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    tag_id = int(form.get("tag_id") or 0)
    action = str(form.get("action") or "add")
    with SessionLocal() as s:
        user = current_user(s, request)
        n = 0
        for rid in ids:
            rec = s.get(Record, rid)
            if not _taggable(s, user, rec):
                continue
            if (T.add_tag(s, rec, tag_id, user) if action == "add" else T.remove_tag(s, rec, tag_id, user)):
                n += 1
        s.commit()
        from ..db import Tag
        tag = s.get(Tag, tag_id)
        if not ids:
            flash(request, "Tick one or more contacts first.", True)
        else:
            flash(request, f"Tag “{tag.name if tag else '?'}” {'added to' if action == 'add' else 'removed from'} "
                           f"{n} contact{'s' if n != 1 else ''}.")
    return back(request, "/contacts")


@router.post("/records/{rid}/cardfields", response_class=HTMLResponse)
async def card_fields_save(request: Request, rid: int):
    """“Short Card Shows…”: the fields on a directory's short cards, for everyone or only for me."""
    form = await request.form()
    gid = int(form.get("group_id") or 0)
    keys = [k for k in form.getlist("fields") if k][:3]
    scope = str(form.get("scope") or "me")
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = s.get(Record, rid)
        group = s.get(Group, gid)
        if not rec or not group or not C.can_see_record(s, user, rec) or not can(user, "view", gid):
            raise Forbidden
        valid = {f.key for f in group.fields}
        keys = [k for k in keys if k in valid]
        mine = dict((user.prefs or {}).get("cardfields") or {})
        if scope == "dir":
            require(user, "manage_dirs")
            for f in group.fields:
                f.card = f.key in keys
            mine.pop(str(gid), None)
            msg = f"Short cards in {group.name} now show: {', '.join(keys) or 'name and city only'} (for everyone)."
        else:
            mine[str(gid)] = keys
            msg = "Your short cards in this directory now show the ticked fields (only for you)."
        user.prefs = {**(user.prefs or {}), "cardfields": mine}
        s.commit()
        return _card(request, s, user, rec, ctx_gid=gid, notice=msg + " Reload the page to see the cards.")


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
