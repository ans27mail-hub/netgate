"""Filter chips for All contacts, a directory and the Inbox: read from the address bar, applied in SQL."""
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import Text, cast, exists, or_, select

from ..contacts import METHOD_LABELS, search_clause
from ..db import InboxItem, Membership, Record, RecordTag

HAS = {"email": "email", "phone": "phone", "website": "website", "social": "social links", "whatsapp": "WhatsApp"}
COMPLETE = {"100": "complete", "50": "≥ 50% complete", "missing": "missing fields"}
ADDED = {"7": "last 7 days", "30": "last 30 days", "90": "last 90 days"}
MULTI = ("dir", "country", "city", "has", "method", "tag")


class Filters:
    def __init__(self, request, fields=None, groups=None, keep=("view", "sort"), tags=None):
        qp = request.query_params
        self.raw = [(k, v) for k, v in qp.multi_items() if v != ""]
        self.q = qp.get("q", "").strip()
        self.values = {k: [v for kk, v in self.raw if kk == k] for k in MULTI}
        self.complete = qp.get("complete", "")
        self.added = qp.get("added", "")
        self.kw = qp.get("kw", "").strip()
        self.fields = {f.key: f for f in (fields or []) if f.filter}
        self.fvals = {k[2:]: v for k, v in self.raw if k.startswith("f_") and k[2:] in self.fields}
        self.groups = {g.id: g for g in (groups or [])}
        self.tags = {t.id: t for t in (tags or [])}
        self.keep = keep

    # ---- SQL ----
    def apply(self, stmt, email_keys=("contact_email", "email"), phone_keys=("phone", "whatsapp")):
        if self.q:
            stmt = stmt.where(search_clause(self.q))
        dirs = [int(d) for d in self.values["dir"] if d.isdigit()]
        if dirs:
            stmt = stmt.where(Record.id.in_(select(Membership.record_id).where(Membership.group_id.in_(dirs))))
        for key in ("country", "city"):
            vals = self.values[key]
            if vals:
                stmt = stmt.where(or_(*[Record.data[key].astext.ilike(v) for v in vals]))
        for h in self.values["has"]:
            if h == "email":
                stmt = stmt.where(or_(*[Record.data[k].astext.contains("@") for k in email_keys]))
            elif h == "phone":
                stmt = stmt.where(or_(*[Record.data[k].astext != "" for k in phone_keys]))
            elif h == "whatsapp":
                stmt = stmt.where(Record.data["whatsapp"].astext != "")
            elif h == "website":
                stmt = stmt.where(Record.domain.is_not(None))
            elif h == "social":
                stmt = stmt.where(cast(Record.social, Text) != "{}")
        tag_ids = [int(x) for x in self.values["tag"] if x.isdigit()]
        if tag_ids:
            stmt = stmt.where(Record.id.in_(select(RecordTag.record_id).where(RecordTag.tag_id.in_(tag_ids))))
        methods = self.values["method"]
        if methods:
            conds = [exists().where(InboxItem.record_id == Record.id, InboxItem.method.in_(methods))]
            if "web" in methods:   # contacts from before v0.5 were all found by web search
                conds.append(~exists().where(InboxItem.record_id == Record.id))
            stmt = stmt.where(or_(*conds))
        if self.kw:
            like = f"%{self.kw}%"
            stmt = stmt.where(or_(Record.topic.ilike(like),
                                  exists().where(InboxItem.record_id == Record.id, InboxItem.keyword.ilike(like))))
        if self.added in ADDED:
            stmt = stmt.where(Record.created_at >= datetime.utcnow() - timedelta(days=int(self.added)))
        for key, value in self.fvals.items():
            f = self.fields[key]
            stmt = stmt.where(Record.data.contains({key: [value]} if f.type == "list" else {key: value}))
        return stmt

    def keep_complete(self, records, fmap):
        if self.complete not in COMPLETE:
            return records
        out = []
        for r in records:
            _, filled, total = fmap.get(r.id, ([], 0, 0))
            pct = filled * 100 / total if total else 100
            if (self.complete == "100" and filled >= total) or (self.complete == "50" and pct >= 50) \
                    or (self.complete == "missing" and filled < total):
                out.append(r)
        return out

    # ---- chips ----
    def without(self, key, value=None) -> str:
        items = [(k, v) for k, v in self.raw if not (k == key and (value is None or v == value))]
        return "?" + urlencode(items) if items else "?"

    def chips(self) -> list[tuple[str, str, str]]:
        out = []
        for d in self.values["dir"]:
            g = self.groups.get(int(d)) if d.isdigit() else None
            out.append(("Directory", g.name if g else d, self.without("dir", d)))
        for key, label in (("country", "Country"), ("city", "City")):
            for v in self.values[key]:
                out.append((label, v, self.without(key, v)))
        for h in self.values["has"]:
            out.append(("Has", HAS.get(h, h), self.without("has", h)))
        for x in self.values["tag"]:
            tg = self.tags.get(int(x)) if x.isdigit() else None
            out.append(("Tag", tg.name if tg else x, self.without("tag", x)))
        for m in self.values["method"]:
            out.append(("Found by", METHOD_LABELS.get(m, m), self.without("method", m)))
        if self.kw:
            out.append(("Keyword", self.kw, self.without("kw")))
        if self.complete in COMPLETE:
            out.append(("Complete", COMPLETE[self.complete], self.without("complete")))
        if self.added in ADDED:
            out.append(("Added", ADDED[self.added], self.without("added")))
        for key, v in self.fvals.items():
            out.append((self.fields[key].name, v, self.without(f"f_{key}", v)))
        return out

    def active(self) -> bool:
        return bool(self.q or self.chips())

    def hidden(self, skip=()) -> list[tuple[str, str]]:
        """Current parameters, for forms that add one more filter."""
        return [(k, v) for k, v in self.raw if k not in skip]

    def qs(self, skip=("view", "sort")) -> str:
        items = [(k, v) for k, v in self.raw if k not in skip]
        return urlencode(items)


def distinct_values(s, key: str, base_stmt, limit: int = 300) -> list[str]:
    vals = s.scalars(base_stmt.with_only_columns(Record.data[key].astext).distinct().limit(2000)).all()
    return sorted({str(v).strip() for v in vals if v and str(v).strip()}, key=str.lower)[:limit]
