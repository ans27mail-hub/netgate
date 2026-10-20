"""Verify and Company profile (v1.0).

Verify: open again (not from the cache) the pages each value came from and check, by code first, that the value
is still there. When it is not, code looks for a new value on that page; only then the local AI is asked for that
one field. Every value gets a status: same / changed (with the new value) / gone (page could not be read) /
not_found. Nothing changes by itself: a person clicks Accept New Value or Keep Old (Company page).

Profile: read the company's website (home page and a few product / about pages) and ask the AI for a short
profile — what kind of company, product categories (from the list in Settings → Product Categories), main
products, materials, markets, certifications — and a list of products. Products found earlier by NetGate are
replaced; products a person added stay.
"""
import re
from datetime import datetime

from sqlalchemy import delete, select

from . import contacts, crawl, extract, pages
from .db import Product, Record, SessionLocal, get_setting, set_setting

STATUS_LABELS = {"same": "Still the same", "changed": "Changed", "gone": "Page could not be read",
                 "not_found": "Not found on the page any more", "kept": "Kept (checked by a person)",
                 "accepted": "New value accepted"}

DEFAULT_CATEGORIES = [
    "Motorbike Leather Jackets", "Motorbike Textile Jackets", "Motorbike Leather Suits", "Motorbike Gloves",
    "Motorbike Trousers", "Motorbike Boots", "Motorbike Vests & Waistcoats", "Kids Motorbike Wear",
    "Protectors & Armour", "Rain & Hi-Vis Wear", "Helmets", "Cycling Gloves", "Sports Gloves",
    "Work & Safety Gloves", "Fashion Leather Jackets", "Leather Bags & Accessories", "Sportswear & Uniforms",
    "Other",
]


def categories(s) -> list[str]:
    cats = get_setting(s, "product_categories", None)
    return list(cats) if isinstance(cats, list) and cats else list(DEFAULT_CATEGORIES)


def save_categories(s, text: str) -> list[str]:
    cats = list(dict.fromkeys(c.strip()[:120] for c in (text or "").splitlines() if c.strip()))[:200]
    set_setting(s, "product_categories", cats or list(DEFAULT_CATEGORIES))
    return cats


def how_found(src: str) -> str:
    """Plain words for where a value came from (its source)."""
    v = (src or "").strip()
    low = v.lower()
    if not v:
        return "Unknown"
    if low.startswith("edited by"):
        return "Typed in by " + v[10:]
    if low.startswith("added by") or "csv" in low:
        return "Added by hand"
    if low.startswith("http"):
        if "ebay." in low:
            return "eBay"
        return "Read from a page"
    if "search result" in low:
        return "Search results"
    return v[:60]


def _plain(v) -> str:
    if isinstance(v, list):
        v = " ".join(str(x) for x in v)
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def on_page(field, value, page) -> bool:
    """Is this value still on the page? Phones compare digits; emails and links ignore case."""
    hay = ((page.html or "") + " " + (page.text or "")).lower()
    if not value:
        return False
    if field and field.type == "phone" or (isinstance(value, str) and re.fullmatch(r"[+\d][\d\s().-]{6,}", value)):
        digits = re.sub(r"\D", "", str(value))[-8:]
        return bool(digits) and digits in re.sub(r"\D", "", hay)
    if isinstance(value, list):
        return all(_plain(x) in hay for x in value if str(x).strip())
    text = _plain(value)
    if text.startswith("http"):
        text = re.sub(r"^https?://(www\.)?", "", text).rstrip("/")
    return text in hay or text in re.sub(r"\s+", " ", hay)


def _ask_field(ctx, rec_name, field, page) -> object:
    from .jobs import TYPE_HINTS, ask, clean
    prompt = (f"This page belongs to the company “{rec_name}”. Find its {field.name}"
              + (f" ({field.description})" if getattr(field, "description", "") else "") + ".\n"
              f"Answer JSON: {{\"value\": {TYPE_HINTS.get(field.type, 'short text, or null')}}}. "
              "Use null when the page does not say it. Do not guess.\n\nPAGE:\n" + (page.text or "")[:8000])
    data = ask(ctx, prompt, page.final_url or page.url)
    return clean(field, (data or {}).get("value")) if isinstance(data, dict) else None


def verify(ctx, record_id: int, keys: list[str] | None = None) -> dict:
    """Check the saved values again. Returns counts per status."""
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return {}
        fields = {f.key: f for f in contacts.fields_for(s, rec)}
        data, src, name = dict(rec.data or {}), dict(rec.sources or {}), rec.title
    ctx.group_id = ctx.group_id or None
    todo = {}
    for k, v in data.items():
        if contacts.empty(v) or (keys and k not in keys):
            continue
        url = str(src.get(k) or "")
        if url.startswith("http"):
            todo.setdefault(url, []).append(k)
    results, counts = {}, {}
    for url, ks in todo.items():
        ctx.check()
        page = crawl.get_page(url, use_cache=False)
        ok = ctx.count_page(page)
        page.read_id = pages.record(page, ctx.job_id, "verify", ctx.group_id, record_id) \
            if ctx.job_id is not None else None
        info = extract.analyze(page.html, page.text, page.final_url or page.url) if ok else {}
        for k in ks:
            f, old = fields.get(k), data.get(k)
            if not ok:
                res = {"status": "gone"}
            elif on_page(f, old, page):
                res = {"status": "same"}
            else:
                new = None
                if f:
                    new = extract.fill_fields([f], info, {}, data.get("website")).get(k)
                    if contacts.empty(new) and f.source != "manual":
                        new = _ask_field(ctx, name, f, page)
                if not contacts.empty(new) and _plain(new) == _plain(old):
                    res = {"status": "same"}   # written differently on the page (e.g. “PK” → Pakistan)
                elif not contacts.empty(new):
                    res = {"status": "changed", "new": new}
                else:
                    res = {"status": "not_found"}
            res.update({"at": datetime.utcnow().isoformat(timespec="seconds"), "page": url})
            results[k] = res
            counts[res["status"]] = counts.get(res["status"], 0) + 1
        pages.add_found(getattr(page, "read_id", None), verify={k: results[k]["status"] for k in ks})
        ctx.trace("note", url, text="Verify: " + ", ".join(f"{k} {results[k]['status']}" for k in ks))
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if rec:
            meta = dict(rec.meta or {})
            for k, res in results.items():
                m = dict(meta.get(k) or {})
                m["verify"] = res
                if res["status"] == "same":
                    m["checked"] = res["at"]
                meta[k] = m
            meta["_verified"] = datetime.utcnow().isoformat(timespec="seconds")
            rec.meta = meta
            parts = [f"{n} {STATUS_LABELS[st].lower()}" for st, n in counts.items()]
            contacts.add_history(rec, "Verified: " + (", ".join(parts) if parts else "no values with a page to check"))
            s.commit()
    ctx.stats["fields"] += len(results)
    return counts


# ---------- profile and products ----------

PRODUCT_WORDS = ("product", "shop", "catalog", "collection", "range", "about", "company", "gloves", "jacket")


def _profile_pages(website: str, limit: int = 4) -> list[str]:
    home = crawl.get_page(website)
    urls = [website]
    if home.ok:
        cands = [u for u, _ in crawl.links(home.html, home.final_url or website)]
        dom = (website.split("//")[-1].split("/")[0]).replace("www.", "")
        cands = [u for u in cands if dom in u and any(w in u.lower() for w in PRODUCT_WORDS)]
        urls += list(dict.fromkeys(cands))[: limit - 1]
    return urls


def _image_for(html: str, base: str, product: str) -> str:
    """An <img> whose alt / title / file name mentions the product (only the link is kept)."""
    words = [w for w in re.findall(r"[a-z0-9]+", product.lower()) if len(w) > 2][:4]
    if not words or not html:
        return ""
    from urllib.parse import urljoin
    for m in re.finditer(r"<img\b[^>]*>", html, re.I):
        tag = m.group(0)
        src = re.search(r"""\b(?:data-src|src)=["']([^"']+)["']""", tag, re.I)
        if not src:
            continue
        hay = tag.lower()
        if sum(w in hay for w in words) >= max(1, len(words) - 1):
            return urljoin(base, src.group(1))[:1000]
    return ""


def profile(ctx, record_id: int) -> int:
    """Build the short profile and product list from the company's website. Returns the number of products."""
    from .jobs import ask
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return 0
        website, name, cats = str((rec.data or {}).get("website") or ""), rec.title, categories(s)
    if not website.startswith("http"):
        with SessionLocal() as s:
            rec = s.get(Record, record_id)
            rec.profile = {**(rec.profile or {}), "note": "No website saved, so no profile could be made.",
                           "at": datetime.utcnow().isoformat(timespec="seconds")}
            s.commit()
        return 0
    texts, htmls, read = [], [], []
    for url in _profile_pages(website):
        ctx.check()
        page, ok = ctx.read(url, "company", record_id)
        if ok:
            texts.append(f"--- {page.final_url or url}\n{(page.text or '')[:5000]}")
            htmls.append((page.html or "", page.final_url or url))
            read.append(page.final_url or url)
    if not texts:
        return 0
    prompt = (f"These pages are from the website of the company “{name}”.\n"
              "Write a short profile. Answer JSON with:\n"
              '{"type": "manufacturer / trader / retailer / brand / other", '
              '"summary": "two plain sentences", '
              f'"categories": [product categories, ONLY from this list: {", ".join(cats)}], '
              '"main_products": [up to 8 short names], "materials": [..], "markets": [countries or regions they sell to], '
              '"certifications": [..], "founded": "year or null", '
              '"products": [{"name": "..", "category": "one of the list", "price": "as written or null", '
              '"moq": "minimum order as written or null"}] (up to 30 real products named on the pages)}\n'
              "Use only what the pages say. Use [] or null when they do not say it.\n\n" + "\n\n".join(texts)[:16000])
    data = ask(ctx, prompt, website) or {}
    if not isinstance(data, dict):
        data = {}

    def strs(v, n=12):
        return [str(x)[:80] for x in (v or []) if str(x).strip()][:n] if isinstance(v, list) else []
    prof = {"type": str(data.get("type") or "")[:40], "summary": str(data.get("summary") or "")[:600],
            "categories": [c for c in strs(data.get("categories"), 20) if c in cats],
            "main_products": strs(data.get("main_products"), 8), "materials": strs(data.get("materials")),
            "markets": strs(data.get("markets"), 20), "certifications": strs(data.get("certifications")),
            "founded": str(data.get("founded") or "")[:20] if data.get("founded") else "",
            "pages": read, "at": datetime.utcnow().isoformat(timespec="seconds")}
    items = data.get("products") if isinstance(data.get("products"), list) else []
    n = 0
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return 0
        rec.profile = prof
        s.execute(delete(Product).where(Product.record_id == record_id, Product.added_by.is_(None)))
        seen = set()
        for it in items[:30]:
            if not isinstance(it, dict) or not str(it.get("name") or "").strip():
                continue
            pname = str(it["name"]).strip()[:200]
            if pname.lower() in seen:
                continue
            seen.add(pname.lower())
            img, src = "", ""
            for html, url in htmls:
                img = _image_for(html, url, pname)
                if img or pname.lower() in html.lower():
                    src = url
                if img:
                    break
            cat = str(it.get("category") or "")
            s.add(Product(record_id=record_id, name=pname, category=cat if cat in cats else "",
                          image_url=img, source_url=src or website, price=str(it.get("price") or "")[:60],
                          moq=str(it.get("moq") or "")[:60]))
            n += 1
        contacts.add_history(rec, f"Profile made from the website · {n} product{'' if n == 1 else 's'}")
        s.commit()
    ctx.stats["fields"] += n
    return n


def products(s, record_id: int) -> list:
    return s.scalars(select(Product).where(Product.record_id == record_id).order_by(Product.category, Product.name)).all()
