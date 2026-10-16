"""eBay search method, using eBay's official Browse API (keys in Settings → Connections).

Find: search listings for a keyword on each chosen marketplace, group them by seller, then read one listing
per seller to get the seller's details (business sellers in the UK / EU show their business name, address,
email and phone there).
"""
import os
import time
from urllib.parse import quote

import httpx

from .extract import COUNTRIES

API = os.environ.get("EBAY_API_URL", "https://api.ebay.com").rstrip("/")
SCOPE = "https://api.ebay.com/oauth/api_scope"

EBAY_SITES = [("EBAY_GB", "ebay.co.uk", "UK"), ("EBAY_DE", "ebay.de", "Germany"), ("EBAY_IT", "ebay.it", "Italy"),
              ("EBAY_FR", "ebay.fr", "France"), ("EBAY_US", "ebay.com", "USA"), ("EBAY_CA", "ebay.ca", "Canada"),
              ("EBAY_ES", "ebay.es", "Spain"), ("EBAY_AU", "ebay.com.au", "Australia"),
              ("EBAY_NL", "ebay.nl", "Netherlands"), ("EBAY_AT", "ebay.at", "Austria")]
SITE_HOST = {code: host for code, host, _ in EBAY_SITES}
_tokens: dict = {}


class EbayError(Exception):
    pass


def ready(conn: dict) -> bool:
    e = conn.get("ebay") or {}
    return bool(e.get("client_id") and e.get("client_secret"))


def _token(conn: dict) -> str:
    e = conn.get("ebay") or {}
    cid, secret = e.get("client_id"), e.get("client_secret")
    if not cid or not secret:
        raise EbayError("eBay keys are not set up yet. Add them in Settings → Connections.")
    tok, exp = _tokens.get(cid, (None, 0))
    if tok and exp > time.time() + 60:
        return tok
    r = httpx.post(f"{API}/identity/v1/oauth2/token", auth=(cid, secret), timeout=30,
                   data={"grant_type": "client_credentials", "scope": SCOPE})
    if r.status_code in (400, 401):
        raise EbayError("eBay did not accept the keys. Check the App ID and Cert ID in Settings → Connections.")
    r.raise_for_status()
    data = r.json()
    _tokens[cid] = (data["access_token"], time.time() + int(data.get("expires_in") or 7200))
    return data["access_token"]


def _get(conn, site: str, path: str, params: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {_token(conn)}", "X-EBAY-C-MARKETPLACE-ID": site,
               "Accept-Language": "en-GB,en;q=0.8"}
    for attempt in range(2):
        r = httpx.get(f"{API}{path}", params=params, headers=headers, timeout=40)
        if r.status_code == 429 and attempt == 0:   # rate limit: wait once
            time.sleep(5)
            continue
        return r
    return r


def search(conn, site: str, q: str, limit: int, offset: int, business_only: bool, category_id: str = "",
           seller: str = "") -> tuple[dict, str]:
    """One page of listings. Returns (json, note)."""
    filters = []
    if business_only:
        filters.append("sellerAccountTypes:{BUSINESS}")
    if seller:
        filters.append("sellers:{%s}" % seller)
    params = {"q": q, "limit": max(1, min(200, limit)), "offset": offset}
    if category_id:
        params["category_ids"] = category_id
    if filters:
        params["filter"] = ",".join(filters)
    r = _get(conn, site, "/buy/browse/v1/item_summary/search", params)
    note = ""
    if r.status_code == 400 and business_only:   # filter not supported on this marketplace: filter later
        params["filter"] = ",".join(f for f in filters if not f.startswith("sellerAccountTypes"))
        if not params["filter"]:
            params.pop("filter")
        r = _get(conn, site, "/buy/browse/v1/item_summary/search", params)
        note = "business filter not supported here; checked per seller"
    if r.status_code >= 400:
        raise EbayError(f"eBay search failed on {site}: HTTP {r.status_code} {r.text[:200]}")
    return r.json(), note


def get_item(conn, site: str, item_id: str) -> dict:
    r = _get(conn, site, f"/buy/browse/v1/item/{quote(item_id, safe='')}")
    if r.status_code >= 400:
        return {}
    return r.json()


def seller_url(site: str, username: str) -> str:
    return f"https://www.{SITE_HOST.get(site, 'ebay.com')}/usr/{quote(username)}"


def seller_info(site: str, username: str, summary: dict, item: dict) -> dict:
    """Everything we know about a seller, from a listing summary and one full listing."""
    seller = (item.get("seller") or {}) or (summary.get("seller") or {})
    legal = seller.get("sellerLegalInfo") or {}
    addr = legal.get("sellerProvidedLegalAddress") or {}
    loc = item.get("itemLocation") or summary.get("itemLocation") or {}
    country_code = (addr.get("country") or loc.get("country") or "").upper()
    address = ", ".join(x for x in [addr.get("addressLine1"), addr.get("addressLine2"), addr.get("postalCode"),
                                    addr.get("city"), addr.get("countryName") or COUNTRIES.get(country_code)] if x)
    vat = ""
    for v in legal.get("vatDetails") or []:
        if isinstance(v, dict) and v.get("vatId"):
            vat = v["vatId"]
            break
    pct = seller.get("feedbackPercentage") or (summary.get("seller") or {}).get("feedbackPercentage")
    score = seller.get("feedbackScore") or (summary.get("seller") or {}).get("feedbackScore")
    return {
        "username": username,
        "business_name": legal.get("name") or legal.get("businessName") or "",
        "account_type": seller.get("sellerAccountType") or "",
        "feedback_pct": f"{pct}%" if pct not in (None, "") else "",
        "feedback_score": score,
        "country": COUNTRIES.get(country_code, country_code) if country_code else "",
        "city": addr.get("city") or loc.get("city") or "",
        "address": address,
        "email": legal.get("email") or "",
        "phone": legal.get("phone") or "",
        "vat": vat,
        "store_url": seller_url(site, username),
        "site": SITE_HOST.get(site, site),
    }


def find_sellers(conn: dict, opts: dict, query: str, check=lambda: None, note=lambda *a, **k: None):
    """Yield one dict per seller found for a keyword (see seller_info, plus 'products' and 'sites')."""
    e = conn.get("ebay") or {}
    sites = [x for x in (opts.get("sites") or e.get("sites") or []) if x in SITE_HOST]
    per_keyword = int(opts.get("per_keyword") or 200)
    min_fb = int(opts.get("min_feedback") or 0)
    business_only = bool(opts.get("business_only", e.get("business_only", True)))
    max_sellers = int(opts.get("max_sellers") or 60)
    seen_users: set = set()
    for site in sites:
        check()
        sellers: dict = {}
        offset, notes = 0, set()
        while offset < per_keyword:
            data, n = search(conn, site, query, min(200, per_keyword - offset), offset, business_only,
                             str(opts.get("category_id") or ""))
            if n:
                notes.add(n)
            items = data.get("itemSummaries") or []
            note("search", f"{SITE_HOST[site]}: “{query}”", listings=len(items), offset=offset, total=data.get("total"))
            for it in items:
                sel = it.get("seller") or {}
                user = (sel.get("username") or "").strip()
                if not user:
                    continue
                entry = sellers.setdefault(user, {"summary": it, "titles": [], "count": 0})
                entry["count"] += 1
                if len(entry["titles"]) < 8 and it.get("title"):
                    entry["titles"].append(it["title"])
            offset += len(items)
            if len(items) == 0 or offset >= int(data.get("total") or 0):
                break
        ranked = sorted(sellers.items(), key=lambda kv: -int((kv[1]["summary"].get("seller") or {})
                                                             .get("feedbackScore") or 0))
        taken = 0
        for user, entry in ranked:
            if taken >= max_sellers:
                break
            check()
            fb = int((entry["summary"].get("seller") or {}).get("feedbackScore") or 0)
            if fb < min_fb or user.lower() in seen_users:
                continue
            item = get_item(conn, site, entry["summary"].get("itemId") or "")
            info = seller_info(site, user, entry["summary"], item)
            if business_only and info["account_type"] == "INDIVIDUAL":
                note("note", f"Skipped private seller {user}")
                continue
            seen_users.add(user.lower())
            taken += 1
            info["products"] = entry["titles"]
            info["listings"] = entry["count"]
            info["sites"] = [SITE_HOST[site]]
            note("code", info["store_url"], seller=user, found={k: v for k, v in info.items() if v})
            yield info


def lookup_seller(conn: dict, username: str, queries: list[str], sites: list[str] | None = None) -> dict | None:
    """Enrich: details of a known seller. eBay needs a search word, so we try the contact's products/keywords."""
    e = conn.get("ebay") or {}
    for site in [x for x in (sites or e.get("sites") or ["EBAY_GB"]) if x in SITE_HOST]:
        for q in [q for q in queries if q][:4]:
            try:
                data, _ = search(conn, site, q, 3, 0, False, seller=username)
            except EbayError:
                continue
            items = data.get("itemSummaries") or []
            if items:
                item = get_item(conn, site, items[0].get("itemId") or "")
                info = seller_info(site, username, items[0], item)
                info["products"] = [i.get("title") for i in items if i.get("title")]
                info["sites"] = [SITE_HOST[site]]
                return info
    return None


def values_for(fields, info: dict) -> dict:
    """Map seller details onto a directory's fields: by "Filled from", then by field key / type."""
    out = {}
    by_source = {
        "ebay:username": info.get("username"), "ebay:business_name": info.get("business_name"),
        "ebay:feedback_pct": info.get("feedback_pct"), "ebay:feedback_score": info.get("feedback_score"),
        "ebay:country": info.get("country"), "ebay:city": info.get("city"), "ebay:address": info.get("address"),
        "ebay:email": info.get("email"), "ebay:phone": info.get("phone"), "ebay:vat": info.get("vat"),
        "ebay:store_url": info.get("store_url"), "ebay:products": info.get("products"),
        "ebay:sites": info.get("sites"), "method:marketplace": ["eBay"],
    }
    for f in fields:
        v = None
        if f.source in by_source:
            v = by_source[f.source]
        elif f.source in ("manual", "website"):
            continue
        elif f.key == "city":
            v = info.get("city")
        elif f.key == "country":
            v = info.get("country")
        elif f.type == "email" or "email" in f.key:
            v = info.get("email")
        elif f.type == "phone" or any(w in f.key for w in ("phone", "tel", "mobile")):
            v = info.get("phone")
        elif "address" in f.key:
            v = info.get("address")
        elif f.key in ("sells_on", "marketplace", "marketplaces"):
            v = ["eBay"]
        if v in (None, "", []):
            continue
        if f.type == "list" and not isinstance(v, list):
            v = [str(v)]
        elif f.type == "number":
            try:
                v = float(str(v).rstrip("%"))
            except ValueError:
                continue
        elif f.type != "list" and isinstance(v, list):
            v = ", ".join(map(str, v))
        out[f.key] = v
    return out
