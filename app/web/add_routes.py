"""Add contacts by hand: one contact, a pasted list or a CSV file. They go to the Inbox (or straight into the
directory for people who may review), then Enrich runs with the chosen steps."""
import csv
import io
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import contacts as C
from .. import methods
from ..auth import can
from ..db import Group, Record, SessionLocal
from .common import Forbidden, all_groups, current_user, flash, go, render, start_job, templates

router = APIRouter()

NAME_COLS = ("name", "company", "company name", "store", "store name", "shop", "seller", "business")
ALIASES = {"city": ("city", "town"), "country": ("country",), "website": ("website", "web", "url", "site", "homepage"),
           "email": ("email", "e-mail", "mail", "contact email"), "phone": ("phone", "telephone", "tel", "mobile", "whatsapp"),
           "notes": ("notes", "note", "comment", "comments")}


def _targets(s, user):
    return [g for g in all_groups(s) if can(user, "add_contacts", g.id)]


@router.get("/contacts/add", response_class=HTMLResponse)
def add_page(request: Request, tab: str = "one", group: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        targets = _targets(s, user)
        if not targets and not can(user, "add_contacts"):
            raise Forbidden
        return render(request, s, user, "add_contact.html", active_nav="add", help="add-contact",
                      tab=tab if tab in ("one", "list", "csv") else "one", targets=targets, sel_id=group,
                      result=request.session.pop("add_result", None))


@router.get("/contacts/check", response_class=HTMLResponse)
def check(request: Request, name: str = "", website: str = "", links: str = ""):
    """Live duplicate check while typing (HTMX)."""
    with SessionLocal() as s:
        user = current_user(s, request)
        found = []
        if len(name.strip()) >= 3 or website.strip() or links.strip():
            link_map = {}
            for line in links.splitlines():
                line = line.strip()
                if line.startswith("http"):
                    link_map.setdefault(C.classify_link(line), line)
            found = [r for r in C.possible_duplicates(s, name.strip(), website.strip() or link_map.get("website", ""),
                                                      link_map) if C.can_see_record(s, user, r)]
        return templates.TemplateResponse(request, "_dupcheck.html", {"found": found, "name": name})


def _split_links(text: str) -> tuple[dict, dict, str]:
    """Links typed by the user -> (store links, social links, website)."""
    links, social, website = {}, {}, ""
    for raw in re.split(r"[\s,]+", text or ""):
        url = raw.strip()
        if not url:
            continue
        if not url.startswith("http"):
            if "." not in url:
                continue
            url = "https://" + url
        kind = C.classify_link(url)
        if kind in ("ebay", "etsy", "amazon"):
            links.setdefault(kind, url)
        elif kind in ("facebook", "instagram", "linkedin"):
            social.setdefault(kind, url)
        elif kind == "whatsapp":
            social.setdefault("whatsapp", url)
        elif not website:
            website = url
    return links, social, website


def _add_one(s, user, group, row: dict, how: str, accept_now: bool) -> tuple[str, Record | None]:
    """Returns ('added' | 'matched' | 'skipped', record)."""
    name = str(row.get("name") or "").strip()
    if len(name) < 2:
        return "skipped", None
    links, social, website = _split_links(" ".join(str(row.get(k) or "") for k in ("links", "website")))
    fields = list(group.fields) if group else C.common_fields()
    values, sources = {}, {}
    email_key = next((f.key for f in fields if f.type == "email"), None)
    phone_key = next((f.key for f in fields if f.type == "phone"), None)
    plain = {"city": row.get("city"), "country": row.get("country"), "website": website}
    if email_key:
        plain[email_key] = row.get("email")
    if phone_key:
        plain[phone_key] = row.get("phone")
    for f in fields:   # any CSV column named like a field
        v = row.get(f.key) if row.get(f.key) not in (None, "") else row.get(f.name.lower())
        if v not in (None, ""):
            plain.setdefault(f.key, v)
    from ..jobs import clean
    by_key = {f.key: f for f in fields}
    for k, v in plain.items():
        if k in by_key and str(v or "").strip():
            cv = clean(by_key[k], v)
            if not C.empty(cv):
                values[k], sources[k] = cv, f"added by {user.username}"
    ext = {k: C.marketplace_id(k, u) for k, u in links.items() if C.marketplace_id(k, u)}
    rec, created, _ = C.upsert(s, name=name, values=values, sources=sources, social=social, links=links, ext=ext,
                               summary="", source_url="", topic=f"added by hand ({how})",
                               history=f"Added by hand ({how}) by {user.username}", added_by=user.id)
    if row.get("notes"):
        rec.notes = ((rec.notes + "\n") if rec.notes else "") + str(row["notes"]).strip()[:1000]
    if not created:
        C.add_history(rec, f"{user.username} added details by hand ({how})")
        if group and rec.found_by != user.id:
            C.note_existing_hit(s, user.id, rec, group.id, f"added by hand ({how})", None)
    item = C.to_inbox(s, rec, group.id if group else None, method="manual" if how != "CSV" else "csv",
                      keyword="", found_url="")
    if item:
        item.suggest, item.why = "accept", "directory chosen when added"
        if accept_now and group and can(user, "review", group.id):
            C.accept(s, item, user)
    return ("added" if created else "matched"), rec


def _read_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", "replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    out = []
    for r in rows[1:]:
        row = {}
        for h, v in zip(head, r):
            v = v.strip()
            if not v:
                continue
            if h in NAME_COLS and "name" not in row:
                row["name"] = v
                continue
            for key, names in ALIASES.items():
                if h in names and key not in row:
                    row[key] = v
                    break
            else:
                row[h] = v
                row[h.replace(" ", "_")] = v
        if row.get("name"):
            out.append(row)
    return out


def _read_list(text: str) -> list[dict]:
    """Paste: one company per line — name, city, country, website (any part can be left out)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"\t|;|,", line)]
        row = {"name": parts[0]}
        rest = parts[1:]
        for p in rest:
            if not p:
                continue
            if "@" in p:
                row.setdefault("email", p)
            elif p.startswith("http") or re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", p):
                row["links"] = (row.get("links", "") + " " + p).strip()
            elif re.match(r"^\+?[\d\s()-]{7,}$", p):
                row.setdefault("phone", p)
            elif "city" not in row:
                row["city"] = p
            elif "country" not in row:
                row["country"] = p
        out.append(row)
    return out


@router.post("/contacts/add")
async def add(request: Request):
    form = await request.form()
    tab = str(form.get("tab") or "one")
    then = str(form.get("then") or "inbox")          # enrich / inbox / tonight
    gid = int(form.get("group_id") or 0)
    steps = [k for k in form.getlist("steps") if k in methods.ENRICH_STEP_KEYS]
    accept_now = form.get("accept_now") == "on"
    with SessionLocal() as s:
        user = current_user(s, request)
        group = s.get(Group, gid) if gid else None
        if (group and not can(user, "add_contacts", gid)) or (not group and not can(user, "add_contacts")):
            raise Forbidden
        if tab == "csv":
            upload = form.get("file")
            data = await upload.read() if upload and hasattr(upload, "read") else b""
            rows, how = _read_csv(data), "CSV"
        elif tab == "list":
            rows, how = _read_list(str(form.get("list") or "")), "list"
        else:
            rows = [{k: str(form.get(k) or "") for k in ("name", "city", "country", "links", "email", "phone",
                                                         "notes")}]
            how = "form"
        if not rows or not any(r.get("name") for r in rows):
            flash(request, "Type a company name (or paste a list / choose a CSV file with a name column).", True)
            return go(f"/contacts/add?tab={tab}&group={gid}")
        result = {"added": 0, "matched": 0, "skipped": 0}
        recs = []
        for row in rows[:2000]:
            outcome, rec = _add_one(s, user, group, row, how, accept_now)
            result[outcome] += 1
            if rec:
                recs.append(rec)
                if then == "tonight":
                    rec.enrich_tonight = True
        s.commit()
        if then == "enrich" and can(user, "enrich", gid or None):
            for rec in recs[:100]:
                start_job(s, user, "enrich", rec.title, gid or None, record_id=rec.id,
                          params={"steps": steps or methods.ENRICH_STEP_KEYS})
        where = (f"{group.name}" if accept_now and group and can(user, "review", group.id) else "the Inbox")
        msg = (f"{result['added']} new contact{'s' if result['added'] != 1 else ''} added to {where}"
               + (f", {result['matched']} already in NetGate (your details were added to them)" if result["matched"] else "")
               + (f", {result['skipped']} skipped (no name)" if result["skipped"] else "") + ".")
        if then == "enrich":
            msg += " Enrich has started."
        elif then == "tonight":
            msg += " They will be enriched tonight."
        flash(request, msg)
        if len(recs) == 1 and how == "form":
            from urllib.parse import quote_plus
            if accept_now and group and can(user, "review", group.id):
                return go(f"/d/{group.id}?q={quote_plus(recs[0].title)}")
            return go(f"/inbox?q={quote_plus(recs[0].title)}")
    return go(f"/contacts/add?tab={tab}&group={gid}")
