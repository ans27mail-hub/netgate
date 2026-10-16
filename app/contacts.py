"""Contacts, directories and the Inbox.

A contact (Record) exists once. It reaches a directory only when someone accepts it (Membership).
Until then it waits in the Inbox (InboxItem), one item per directory it was found for.
"""
from datetime import datetime

from sqlalchemy import or_, select

from .db import (Decision, Field, Group, InboxItem, Membership, Record, User, name_key,
                 url_domain)

METHOD_LABELS = {"web": "Web search", "directory": "Directory site", "ebay": "eBay search", "etsy": "Etsy search",
                 "amazon": "Amazon search", "manual": "Added by hand", "csv": "CSV import", "recipe": "Custom recipe",
                 "website": "Company website"}

REJECT_REASONS = ["Private seller", "Trader, not manufacturer", "Wrong country", "Not relevant",
                  "Directory / marketplace page", "Duplicate", "Closed / not active"]


def common_fields() -> list[Field]:
    """Fields used when a contact isn't meant for a directory yet ("not sure yet")."""
    return [Field(name="City", key="city", type="text", stage="discover", position=1),
            Field(name="Country", key="country", type="text", stage="discover", position=2),
            Field(name="Website", key="website", type="url", stage="discover", position=3),
            Field(name="Email", key="contact_email", type="email", words="contact, email", position=4),
            Field(name="Phone", key="phone", type="phone", words="phone, contact", position=5)]


def empty(v) -> bool:
    return v in (None, "", [], "Unknown")


def member_ids(s, record_id: int) -> list[int]:
    return list(s.scalars(select(Membership.group_id).where(Membership.record_id == record_id)).all())


def open_item_group_ids(s, record_id: int) -> list[int]:
    return [g for g in s.scalars(select(InboxItem.group_id).where(InboxItem.record_id == record_id,
                                                                   InboxItem.status == "new")).all() if g]


def fields_for(s, record, group=None) -> list[Field]:
    """The fields that matter for this contact: the directory's, or all its directories' together."""
    if group is not None:
        return list(group.fields)
    gids = member_ids(s, record.id) + open_item_group_ids(s, record.id)
    out, seen = [], set()
    for gid in dict.fromkeys(gids):
        g = s.get(Group, gid)
        for f in (g.fields if g else []):
            if f.key not in seen:
                seen.add(f.key)
                out.append(f)
    return out or common_fields()


def completeness_of(record, fields) -> tuple[int, int]:
    data = record.data or {}
    return sum(1 for f in fields if not empty(data.get(f.key))), len(fields)


def add_history(record, text: str):
    record.history = list(record.history or []) + [{"at": datetime.utcnow().isoformat(timespec="seconds"),
                                                    "text": text[:300]}]


# ---------- matching ----------

def find_match(s, nk: str | None, dom: str | None, city: str | None, ext: dict | None = None):
    """The same company already in NetGate: marketplace id, then website, then name (+ city)."""
    for site, ident in (ext or {}).items():
        if ident:
            rec = s.scalar(select(Record).where(Record.ext.contains({site: ident})).limit(1))
            if rec:
                return rec
    if dom:
        rec = s.scalar(select(Record).where(Record.domain == dom).order_by(Record.id).limit(1))
        if rec:
            return rec
    if nk:
        city_l = (city or "").strip().lower()
        for rec in s.scalars(select(Record).where(Record.name_key == nk).order_by(Record.id)).all():
            rec_city = str((rec.data or {}).get("city") or "").strip().lower()
            if not city_l or not rec_city or rec_city == city_l:
                return rec
    return None


def possible_duplicates(s, name: str, website: str = "", links: dict | None = None, limit: int = 5) -> list:
    """For "Add contact": records that look like the same company."""
    found = []
    ext = {}
    for site, url in (links or {}).items():
        ident = marketplace_id(site, url)
        if ident:
            ext[site] = ident
    rec = find_match(s, name_key(name) if name else None, url_domain(website), None, ext)
    if rec:
        found.append(rec)
    nk = name_key(name)
    if nk and len(nk) >= 3:
        for r in s.scalars(select(Record).where(Record.name_key.like(f"%{nk}%")).limit(limit)).all():
            if r not in found:
                found.append(r)
    return found[:limit]


def marketplace_id(site: str, url: str) -> str | None:
    """https://www.ebay.co.uk/usr/acme_store -> acme_store"""
    import re
    url = url or ""
    if site == "ebay":
        m = re.search(r"ebay\.[a-z.]+/(?:usr|str)/([^/?#]+)", url, re.I)
        return m.group(1).lower() if m else None
    if site == "etsy":
        m = re.search(r"etsy\.com/(?:[a-z-]+/)?shop/([^/?#]+)", url, re.I)
        return m.group(1).lower() if m else None
    if site == "amazon":
        m = re.search(r"[?&]seller=([A-Z0-9]+)", url, re.I)
        return m.group(1) if m else None
    return None


def classify_link(url: str) -> str:
    """Which kind of link is this? website / ebay / etsy / amazon / facebook / instagram / linkedin / whatsapp"""
    low = (url or "").lower()
    for kind, needle in (("ebay", "ebay."), ("etsy", "etsy.com"), ("amazon", "amazon."),
                         ("facebook", "facebook.com"), ("instagram", "instagram.com"),
                         ("linkedin", "linkedin.com"), ("whatsapp", "wa.me")):
        if needle in low:
            return kind
    return "website"


# ---------- saving what a search found ----------

def upsert(s, *, name: str, values: dict, sources: dict, social: dict | None = None, links: dict | None = None,
           ext: dict | None = None, summary: str = "", source_url: str = "", topic: str = "",
           job_id: int | None = None, history: str = "", added_by: int | None = None, overwrite: bool = False):
    """Add a new contact or fill the gaps of the existing one. Returns (record, created, changed)."""
    nk = name_key(name)
    dom = url_domain(values.get("website"))
    rec = find_match(s, nk, dom, values.get("city"), ext)
    if rec is None:
        rec = Record(job_id=job_id, topic=topic[:300], title=name[:300], summary=(summary or "")[:1000], facts="",
                     data=dict(values), sources=dict(sources), social=dict(social or {}), links=dict(links or {}),
                     ext=dict(ext or {}), history=[], notes="", source_url=source_url or "", name_key=nk,
                     domain=dom, added_by=added_by)
        if history:
            add_history(rec, history)
        s.add(rec)
        s.flush()
        return rec, True, True
    data, src, soc = dict(rec.data or {}), dict(rec.sources or {}), dict(rec.social or {})
    lnk, ex = dict(rec.links or {}), dict(rec.ext or {})
    changed = False
    for k, v in values.items():
        if not empty(v) and (empty(data.get(k)) or (overwrite and data.get(k) != v)):
            data[k], src[k], changed = v, sources.get(k, source_url), True
    for target, new in ((soc, social), (lnk, links), (ex, ext)):
        for k, v in (new or {}).items():
            if v and not target.get(k):
                target[k], changed = v, True
    if not rec.summary and summary:
        rec.summary, changed = summary[:1000], True
    if changed:
        rec.data, rec.sources, rec.social, rec.links, rec.ext = data, src, soc, lnk, ex
        rec.domain = rec.domain or url_domain(data.get("website"))
    return rec, False, changed


def to_inbox(s, rec, group_id: int | None, *, method: str, keyword: str = "", job_id: int | None = None,
             found_url: str = "", user_id: int | None = None):
    """Put a contact in the Inbox for a directory. Returns the new item, or None when it isn't needed:
    already in that directory, already waiting, or decided for it before (rejected stays rejected)."""
    if group_id and s.get(Membership, (rec.id, group_id)):
        return None
    existing = s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id,
                                                 InboxItem.group_id.is_(None) if group_id is None
                                                 else InboxItem.group_id == group_id)).all()
    if existing:   # waiting, rejected (stays rejected) or already decided for this directory
        return None
    item = InboxItem(record_id=rec.id, group_id=group_id, status="new", method=method, keyword=keyword[:300],
                     job_id=job_id, found_url=found_url or "")
    s.add(item)
    s.flush()
    return item


# ---------- decisions ----------

def snapshot(rec) -> dict:
    return {"name": rec.title, "summary": rec.summary or "", "data": rec.data or {}, "links": rec.links or {},
            "social": rec.social or {}, "domain": rec.domain or "", "source_url": rec.source_url or ""}


def _log(s, user, rec, group_id, decision, reason="", method="", keyword=""):
    s.add(Decision(user_id=user.id if user else None, record_id=rec.id, group_id=group_id, decision=decision,
                   reason=reason or "", method=method or "", keyword=keyword or "", snapshot=snapshot(rec)))


def user_name(s, user_id) -> str:
    if not user_id:
        return "NetGate"
    u = s.get(User, user_id)
    return u.username if u else "(deleted user)"


def accept(s, item: InboxItem, user, group_id: int | None = None):
    """Accept an Inbox item into a directory (its own, or another one chosen by the user)."""
    gid = group_id or item.group_id
    rec = s.get(Record, item.record_id)
    if not gid or not rec:
        return False
    if not s.get(Membership, (rec.id, gid)):
        s.add(Membership(record_id=rec.id, group_id=gid, added_by=user.id if user else None))
    rec.accepted_at = rec.accepted_at or datetime.utcnow()
    rec.group_id = rec.group_id or gid
    item.status, item.decided_at, item.decided_by = "accepted", datetime.utcnow(), user.id if user else None
    if group_id and group_id != item.group_id:   # accepted somewhere else: close the other waiting item too
        for other in s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id, InboxItem.group_id == gid,
                                                       InboxItem.status == "new")).all():
            other.status, other.decided_at = "accepted", datetime.utcnow()
    g = s.get(Group, gid)
    add_history(rec, f"Accepted into {g.name if g else 'a directory'} by {user.username if user else 'NetGate'}")
    _log(s, user, rec, gid, "accept", method=item.method, keyword=item.keyword)
    return True


def reject(s, item: InboxItem, user, reason: str = ""):
    rec = s.get(Record, item.record_id)
    item.status, item.reason = "rejected", (reason or "")[:200]
    item.decided_at, item.decided_by = datetime.utcnow(), user.id if user else None
    if rec:
        _log(s, user, rec, item.group_id, "reject", reason=reason, method=item.method, keyword=item.keyword)


def restore(s, item: InboxItem, user):
    rec = s.get(Record, item.record_id)
    item.status, item.reason, item.decided_at, item.decided_by = "new", "", None, None
    if rec:
        _log(s, user, rec, item.group_id, "restore", method=item.method, keyword=item.keyword)


def add_to_directory(s, rec, group_id: int, user):
    """From All contacts: put an existing contact straight into another directory."""
    if s.get(Membership, (rec.id, group_id)):
        return False
    s.add(Membership(record_id=rec.id, group_id=group_id, added_by=user.id if user else None))
    rec.accepted_at = rec.accepted_at or datetime.utcnow()
    for item in s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id, InboxItem.group_id == group_id,
                                                  InboxItem.status == "new")).all():
        item.status, item.decided_at, item.decided_by = "accepted", datetime.utcnow(), user.id if user else None
    g = s.get(Group, group_id)
    add_history(rec, f"Added to {g.name if g else 'a directory'} by {user.username if user else 'NetGate'}")
    _log(s, user, rec, group_id, "accept", method="manual")
    return True


def move(s, rec, from_ids, to_id: int, user) -> bool:
    """Move a contact out of some directories into another one. Details, history and notes are kept.
    Returns False when there was nothing to do."""
    from_ids = [g for g in dict.fromkeys(from_ids) if g != to_id and s.get(Membership, (rec.id, g))]
    if not from_ids:
        return False
    names = {g.id: g.name for g in s.scalars(select(Group).where(Group.id.in_(from_ids + [to_id]))).all()}
    if not s.get(Membership, (rec.id, to_id)):
        s.add(Membership(record_id=rec.id, group_id=to_id, added_by=user.id if user else None))
    for item in s.scalars(select(InboxItem).where(InboxItem.record_id == rec.id, InboxItem.group_id == to_id,
                                                  InboxItem.status == "new")).all():
        item.status, item.decided_at, item.decided_by = "accepted", datetime.utcnow(), user.id if user else None
    for g in from_ids:
        s.delete(s.get(Membership, (rec.id, g)))
    rec.accepted_at = rec.accepted_at or datetime.utcnow()
    src = ", ".join(names.get(g, "a directory") for g in from_ids)
    add_history(rec, f"Moved from {src} to {names.get(to_id, 'a directory')} by {user.username if user else 'NetGate'}")
    _log(s, user, rec, to_id, "move", reason=f"from {src}", method="manual")
    s.flush()
    return True


def remove_from_directory(s, rec, group_id: int, user):
    m = s.get(Membership, (rec.id, group_id))
    if not m:
        return False
    s.delete(m)
    g = s.get(Group, group_id)
    add_history(rec, f"Removed from {g.name if g else 'a directory'} by {user.username if user else 'NetGate'}")
    _log(s, user, rec, group_id, "remove")
    return True


# ---------- who may see what ----------

def visible_group_ids(user, groups) -> set[int]:
    from .auth import can
    return {g.id for g in groups if can(user, "view", g.id)}


def can_see_record(s, user, rec) -> bool:
    from .auth import can, sees_all_groups
    if sees_all_groups(user) and can(user, "view"):
        return True
    gids = member_ids(s, rec.id) + open_item_group_ids(s, rec.id)
    return any(can(user, "view", g) for g in gids)


def search_clause(q: str):
    from sqlalchemy import Text, cast
    like = f"%{q.strip()}%"
    return or_(Record.title.ilike(like), Record.summary.ilike(like), Record.notes.ilike(like),
               cast(Record.data, Text).ilike(like), Record.domain.ilike(like))

