"""Company page (v1.0): everything about one company on one page — each detail with where and when it was found,
Verify, the short profile, products, pages read, history — and Settings → Product Categories."""
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from .. import contacts as C
from .. import pages
from .. import verify as VF
from ..auth import can
from ..db import Job, Product, Record, SessionLocal
from .common import Forbidden, all_groups, current_user, flash, go, render, require, start_job

router = APIRouter()


def _rec(s, user, rid: int):
    rec = s.get(Record, rid)
    if not rec or not C.can_see_record(s, user, rec) or C.limited_view(user, rec):
        raise Forbidden
    return rec


def _when(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return ""


@router.get("/companies/{rid}", response_class=HTMLResponse)
def company_page(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = _rec(s, user, rid)
        fields = C.fields_for(s, rec)
        meta, src = dict(rec.meta or {}), dict(rec.sources or {})
        rows = []
        for f in fields:
            v = (rec.data or {}).get(f.key)
            m = meta.get(f.key) or {}
            rows.append({"f": f, "value": v, "empty": C.empty(v), "src": src.get(f.key) or "",
                         "how": VF.how_found(src.get(f.key) or "") if not C.empty(v) else "",
                         "at": _when(m.get("at")), "checked": _when(m.get("checked")), "verify": m.get("verify") or {}})
        mids = C.member_ids(s, rec.id)
        gids = mids + C.open_item_group_ids(s, rec.id)
        jobs = s.scalars(select(Job).where(Job.record_id == rec.id, Job.kind.in_(["verify", "profile"]),
                                           Job.status.in_(["queued", "running"]))).all()
        return render(request, s, user, "company.html", active_nav="contacts", help="company-page",
                      r=rec, rows=rows, products=VF.products(s, rec.id), cats=VF.categories(s),
                      read_rows=pages.for_record(s, rec.id, 60), page_summary=pages.summary,
                      PURPOSES=pages.PURPOSES, members=[g for g in all_groups(s) if g.id in mids],
                      may_enrich=C.may_enrich(user, rec, gids[0] if gids else None),
                      may_edit=can(user, "edit"), verified=_when(meta.get("_verified")),
                      profile_at=_when((rec.profile or {}).get("at")), running=jobs, LABELS=VF.STATUS_LABELS,
                      waiting=sum(1 for x in rows if x["verify"].get("status") in ("changed", "not_found", "gone")))


@router.post("/companies/{rid}/{what}")
async def company_action(request: Request, rid: int, what: str):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        rec = _rec(s, user, rid)
        gids = C.member_ids(s, rec.id) + C.open_item_group_ids(s, rec.id)
        if what in ("verify", "profile"):
            if not C.may_enrich(user, rec, gids[0] if gids else None):
                raise Forbidden
            key = str(form.get("key") or "")
            start_job(s, user, what, rec.title, gids[0] if gids else None, record_id=rec.id,
                      params={"keys": [key]} if key else {})
            flash(request, ("Verify started — NetGate opens the pages again and checks each detail."
                            if what == "verify" else "Making the profile from the website. This page shows it when it is done."))
            return go(f"/companies/{rid}")
        require(user, "edit")
        if what in ("accept", "keep"):
            key = str(form.get("key") or "")
            meta = dict(rec.meta or {})
            m = dict(meta.get(key) or {})
            vf = dict(m.get("verify") or {})
            now = datetime.utcnow().isoformat(timespec="seconds")
            if what == "accept" and vf.get("status") == "changed" and not C.empty(vf.get("new")):
                data, src = dict(rec.data or {}), dict(rec.sources or {})
                old = data.get(key)
                data[key], src[key] = vf["new"], vf.get("page") or f"edited by {user.username}"
                rec.data, rec.sources = data, src
                m["at"] = now
                vf["status"] = "accepted"
                C.add_history(rec, f"{key}: new value accepted by {user.username} (was “{old}”)")
            elif what == "accept" and vf.get("status") in ("not_found", "gone"):
                data, src = dict(rec.data or {}), dict(rec.sources or {})
                data.pop(key, None)
                src.pop(key, None)
                rec.data, rec.sources = data, src
                vf["status"] = "accepted"
                C.add_history(rec, f"{key}: removed by {user.username} after Verify")
            else:
                vf["status"] = "kept"
                C.add_history(rec, f"{key}: old value kept by {user.username} after Verify")
            m["verify"], m["checked"] = vf, now
            meta[key] = m
            rec.meta = meta
            s.commit()
            return go(f"/companies/{rid}#f-{key}")
        if what == "product-add":
            name = str(form.get("name") or "").strip()
            if not name:
                flash(request, "Type the product's name.", True)
                return go(f"/companies/{rid}#products")
            cats = VF.categories(s)
            cat = str(form.get("category") or "")
            s.add(Product(record_id=rec.id, name=name[:200], category=cat if cat in cats else "",
                          image_url=str(form.get("image_url") or "").strip()[:1000],
                          source_url=str(form.get("source_url") or "").strip()[:1000],
                          price=str(form.get("price") or "").strip()[:60], moq=str(form.get("moq") or "").strip()[:60],
                          added_by=user.id))
            C.add_history(rec, f"Product “{name[:80]}” added by {user.username}")
            s.commit()
            flash(request, "Product added.")
            return go(f"/companies/{rid}#products")
        if what == "product-delete":
            p = s.get(Product, int(form.get("pid") or 0))
            if p and p.record_id == rec.id:
                s.delete(p)
                s.commit()
                flash(request, "Product removed.")
            return go(f"/companies/{rid}#products")
    raise Forbidden


@router.get("/settings/product-categories", response_class=HTMLResponse)
def product_categories(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        return render(request, s, user, "product_categories.html", active_nav="prodcats", help="company-page",
                      cats=VF.categories(s), defaults=VF.DEFAULT_CATEGORIES, all=all_groups(s))


@router.post("/settings/product-categories")
async def product_categories_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        if form.get("reset"):
            VF.save_categories(s, "\n".join(VF.DEFAULT_CATEGORIES))
        else:
            VF.save_categories(s, str(form.get("cats") or ""))
        s.commit()
        flash(request, "Product categories saved.")
    return go("/settings/product-categories")


