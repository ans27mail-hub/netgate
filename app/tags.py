"""Tags on contacts: labels like “Hot lead” with a colour. A contact can have several; the tag highest in the
order (lowest position) decides the card's colour."""
from sqlalchemy import func, select

from .contacts import add_history, member_ids
from .db import RecordTag, Tag

PALETTE = [("Red", "#c43d3d"), ("Orange", "#c27a12"), ("Yellow", "#a8860b"), ("Green", "#2f8f5b"),
           ("Teal", "#0f766e"), ("Blue", "#2457d6"), ("Purple", "#6d4bc4"), ("Pink", "#b8407a"),
           ("Grey", "#7a808c"), ("Black", "#16181d")]


def all_tags(s) -> list[Tag]:
    return list(s.scalars(select(Tag).order_by(Tag.position, Tag.id)).all())


def usable_in(tag, group_ids) -> bool:
    """A tag limited to some directories can only be put on contacts in those directories."""
    return tag.all_groups or not group_ids or bool(set(tag.group_ids or []) & set(group_ids))


def tags_map(s, record_ids) -> dict[int, list[Tag]]:
    """record id -> its tags, strongest first."""
    out: dict = {}
    ids = [r for r in record_ids if r]
    if not ids:
        return out
    rows = s.execute(select(RecordTag.record_id, Tag).join(Tag, Tag.id == RecordTag.tag_id)
                     .where(RecordTag.record_id.in_(ids)).order_by(Tag.position, Tag.id)).all()
    for rid, tag in rows:
        out.setdefault(rid, []).append(tag)
    return out


def counts(s, record_ids_select=None) -> dict[int, int]:
    """tag id -> number of contacts (only among `record_ids_select`, a SELECT of record ids, if given)."""
    q = select(RecordTag.tag_id, func.count(RecordTag.record_id)).group_by(RecordTag.tag_id)
    if record_ids_select is not None:
        q = q.where(RecordTag.record_id.in_(record_ids_select))
    return dict(s.execute(q).all())


def tint(tags) -> tuple[str, str] | None:
    """(background, border) for a card from its strongest colouring tag."""
    for t in tags or []:
        if t.color_card:
            return soft(t.color, 0.07), soft(t.color, 0.30)
    return None


def soft(hex_color: str, alpha: float) -> str:
    """The colour mixed into the card colour of the current theme (alpha = share of the colour), so tints
    look right on light and dark themes."""
    h = (hex_color or "#2457d6").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        h = "2457d6"
    return f"color-mix(in srgb, #{h.lower()} {round(alpha * 100)}%, var(--card))"


def set_tags(s, rec, tag_ids, user) -> tuple[list[str], list[str]]:
    """Give the contact exactly these tags. Returns (added names, removed names)."""
    want = set(tag_ids)
    have = {rt.tag_id: rt for rt in s.scalars(select(RecordTag).where(RecordTag.record_id == rec.id)).all()}
    by_id = {t.id: t for t in all_tags(s)}
    gids = member_ids(s, rec.id)
    added, removed = [], []
    for tid in want - set(have):
        tag = by_id.get(tid)
        if tag and usable_in(tag, gids):
            s.add(RecordTag(record_id=rec.id, tag_id=tid, added_by=user.id if user else None))
            added.append(tag.name)
    for tid in set(have) - want:
        s.delete(have[tid])
        removed.append(by_id[tid].name if tid in by_id else "a tag")
    who = user.username if user else "NetGate"
    for n in added:
        add_history(rec, f"Tagged {n} by {who}")
    for n in removed:
        add_history(rec, f"Tag {n} removed by {who}")
    return added, removed


def add_tag(s, rec, tag_id, user) -> bool:
    current = {rt.tag_id for rt in s.scalars(select(RecordTag).where(RecordTag.record_id == rec.id)).all()}
    if tag_id in current:
        return False
    return bool(set_tags(s, rec, current | {tag_id}, user)[0])


def remove_tag(s, rec, tag_id, user) -> bool:
    current = {rt.tag_id for rt in s.scalars(select(RecordTag).where(RecordTag.record_id == rec.id)).all()}
    if tag_id not in current:
        return False
    set_tags(s, rec, current - {tag_id}, user)
    return True


def tag_order_key(tags_by_rec, rid) -> tuple:
    tags = tags_by_rec.get(rid) or []
    return (0, tags[0].position, tags[0].id) if tags else (1, 0, 0)

