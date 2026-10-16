"""Code-first extraction: things a pattern finds more reliably than an AI.

Emails, phone numbers, WhatsApp, social links and the business data many sites embed (schema.org JSON-LD).
"""
import json
import re
from urllib.parse import parse_qs, unquote, urlparse

from .crawl import SOCIAL, links, skip, social_kind
from .db import url_domain

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
PHONE = re.compile(r"(?:(?<=\s)|(?<=^)|(?<=[:(]))(\+\d[\d\s().-]{7,18}\d)")
JUNK_EMAIL = ("example.", "sentry", "wixpress", "domain.com", "email.com", "yourcompany", "@2x", ".png", ".jpg",
              ".gif", ".webp", ".svg", "u003e", "noreply", "no-reply", "@sentry")
SOCIAL_JUNK = ("sharer", "share.php", "/share", "intent/", "dialog/", "/plugins/", "/tr?", "/policies",
               "/legal", "/help", "login", "/hashtag/", "/explore", "/p/", "/reel/", "/stories/", "/watch")

COUNTRIES = {
    "PK": "Pakistan", "GB": "United Kingdom", "UK": "United Kingdom", "DE": "Germany", "IT": "Italy",
    "FR": "France", "US": "United States", "USA": "United States", "CA": "Canada", "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "AT": "Austria", "CH": "Switzerland", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "FI": "Finland", "PL": "Poland", "PT": "Portugal", "IE": "Ireland", "CZ": "Czech Republic",
    "CN": "China", "IN": "India", "BD": "Bangladesh", "VN": "Vietnam", "TR": "Turkey", "AE": "United Arab Emirates",
    "AU": "Australia", "NZ": "New Zealand", "JP": "Japan", "KR": "South Korea", "GR": "Greece", "HU": "Hungary",
    "RO": "Romania", "LK": "Sri Lanka", "TH": "Thailand", "ID": "Indonesia", "MY": "Malaysia", "MX": "Mexico",
    "BR": "Brazil", "ZA": "South Africa", "SA": "Saudi Arabia",
}


def _cf_decode(hexstr: str) -> str:
    """Cloudflare 'email protection' hides addresses in data-cfemail; this undoes it."""
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def emails(html: str, text: str = "") -> list[str]:
    found = []
    for m in re.findall(r"mailto:([^\"'?>\s]+)", html or "", re.I):
        found.append(unquote(m))
    for h in re.findall(r"data-cfemail=[\"']([0-9a-fA-F]+)", html or ""):
        found.append(_cf_decode(h))
    found += EMAIL.findall(text or "")
    found += EMAIL.findall(re.sub(r"(?s)<[^>]+>", " ", html or ""))
    out = []
    for e in found:
        e = e.strip().strip(".,;:").lower()
        if EMAIL.fullmatch(e) and not any(j in e for j in JUNK_EMAIL) and e not in out:
            out.append(e)
    return out[:10]


def _clean_phone(p: str) -> str:
    p = re.sub(r"[^\d+()\s.-]", "", p).strip()
    return re.sub(r"\s+", " ", p)


def phones(html: str, text: str = "") -> list[str]:
    found = [unquote(m) for m in re.findall(r"tel:([^\"'>]+)", html or "", re.I)]
    found += PHONE.findall(text or "")
    out, seen = [], set()
    for p in found:
        p = _clean_phone(p)
        digits = re.sub(r"\D", "", p)
        if 8 <= len(digits) <= 15 and digits not in seen:
            seen.add(digits)
            out.append(p)
    return out[:5]


def whatsapp(html: str) -> list[str]:
    out = []
    for m in re.findall(r"(?:wa\.me/|whatsapp\.com/send\?phone=|whatsapp://send\?phone=)\+?(\d{8,15})", html or "", re.I):
        n = "+" + m
        if n not in out:
            out.append(n)
    return out[:3]


def social_links(html: str, base: str) -> dict:
    out = {}
    for url, _ in links(html, base):
        kind = social_kind(url)
        if not kind or kind in out:
            continue
        low = url.lower()
        path = urlparse(low).path.strip("/")
        if not path or any(j in low for j in SOCIAL_JUNK):
            continue
        if kind == "linkedin" and not path.startswith(("company/", "in/", "showcase/")):
            continue
        out[kind] = url.split("?")[0].rstrip("/")
    return out


ORG_TYPES = ("organization", "localbusiness", "corporation", "store", "onlinestore", "onlinebusiness",
             "manufacturer", "wholesalestore", "clothingstore", "sportinggoodsstore", "shoestore", "professionalservice")


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for k in ("@graph", "publisher", "brand", "seller", "author", "provider", "manufacturer"):
            if k in node:
                yield from _walk(node[k])


def schema_org(html: str) -> dict:
    """Business details from <script type="application/ld+json">: name, url, phone, email, address, sameAs."""
    best: dict = {}
    for raw in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html or "", re.I | re.S):
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            continue
        for node in _walk(data):
            types = node.get("@type")
            types = [t.lower() for t in (types if isinstance(types, list) else [types]) if isinstance(t, str)]
            if not any(t in ORG_TYPES for t in types):
                continue
            addr = node.get("address") or {}
            if isinstance(addr, list):
                addr = addr[0] if addr else {}
            if isinstance(addr, str):
                addr = {"streetAddress": addr}
            country = addr.get("addressCountry") if isinstance(addr, dict) else None
            if isinstance(country, dict):
                country = country.get("name")
            org = {
                "name": node.get("name"), "url": node.get("url"),
                "telephone": node.get("telephone"), "email": (node.get("email") or "").replace("mailto:", "") or None,
                "street": addr.get("streetAddress") if isinstance(addr, dict) else None,
                "city": addr.get("addressLocality") if isinstance(addr, dict) else None,
                "postcode": addr.get("postalCode") if isinstance(addr, dict) else None,
                "country": COUNTRIES.get(str(country).upper(), country) if country else None,
                "same_as": [u for u in (node.get("sameAs") or []) if isinstance(u, str)]
                if isinstance(node.get("sameAs"), list) else ([node["sameAs"]] if isinstance(node.get("sameAs"), str) else []),
            }
            score = sum(1 for v in org.values() if v)
            if score > sum(1 for v in best.values() if v):
                best = org
    return best


def external_website(html: str, base: str, name: str = "") -> str | None:
    """On a directory profile page: the link that leads to the company's own website."""
    host = url_domain(base)
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", (name or "").lower()) if t not in ("ltd", "pvt", "the", "and")]
    best, best_score = None, 0
    for url, text in links(html, base):
        d = url_domain(url)
        if not d or d == host or skip(url) or social_kind(url) or not url.startswith("http"):
            continue
        q = parse_qs(urlparse(url).query)
        for key in ("url", "u", "target", "redirect"):   # unwrap "go.php?url=…" style links
            if q.get(key) and q[key][0].startswith("http"):
                url, d = q[key][0], url_domain(q[key][0])
        label = text.lower()
        score = 1
        if any(w in label for w in ("website", "visit", "homepage", "web site", "www", "site")):
            score += 3
        if d and any(t in d for t in tokens):
            score += 4
        if score > best_score:
            best, best_score = url, score
    return best if best_score >= 4 else None


def analyze(html: str, text: str, base: str) -> dict:
    org = schema_org(html)
    soc = social_links(html, base)
    for u in org.get("same_as") or []:
        kind = social_kind(u)
        if kind and kind not in soc:
            soc[kind] = u
    return {"emails": emails(html, text), "phones": phones(html, text), "whatsapp": whatsapp(html),
            "social": soc, "org": org}


def _country(v):
    if not v:
        return None
    return COUNTRIES.get(str(v).strip().upper(), str(v).strip())


def fill_fields(fields, found: dict, data: dict, website: str | None = None) -> dict:
    """Values for the group's still-empty fields that code could find. {key: value}."""
    out = {}
    org = found.get("org") or {}
    own = url_domain(website) if website else None

    def empty(v):
        return v in (None, "", [], "Unknown")

    for f in fields:
        if not empty(data.get(f.key)):
            continue
        key, typ = f.key.lower(), f.type
        value = None
        if "whatsapp" in key:
            value = (found.get("whatsapp") or [None])[0]
        elif typ == "email" or "email" in key:
            mails = ([org["email"].lower()] if org.get("email") else []) + list(found.get("emails") or [])
            if own:
                mine = [m for m in mails if m.split("@")[-1].endswith(own)]
                mails = mine or mails
            value = mails[0] if mails else None
        elif typ == "phone" or any(w in key for w in ("phone", "tel", "mobile")):
            value = org.get("telephone") or (found.get("phones") or [None])[0]
        elif key in ("website", "own_website", "web", "site") or (typ == "url" and "web" in key):
            u = org.get("url")
            value = u if u and not skip(u) else None
        elif key == "city":
            value = org.get("city")
        elif key == "country":
            value = _country(org.get("country"))
        elif "address" in key:
            parts = [org.get("street"), org.get("postcode"), org.get("city"), _country(org.get("country"))]
            value = ", ".join(str(p) for p in parts if p) or None
        if not empty(value):
            out[f.key] = str(value).strip()[:300]
    return out


__all__ = ["analyze", "emails", "phones", "whatsapp", "social_links", "schema_org", "external_website",
           "fill_fields", "SOCIAL"]
