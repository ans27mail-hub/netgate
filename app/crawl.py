"""Search (SearXNG) and page reading."""
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from .db import url_domain

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NetGate/0.3; directory research)",
           "Accept-Language": "en;q=0.9"}

# Sites that never help: videos, images, shops, and social sites that need a login to read.
SKIP_DOMAINS = ("youtube.com", "youtu.be", "pinterest.", "tiktok.com", "facebook.com", "instagram.com",
                "x.com", "twitter.com", "amazon.", "ebay.", "aliexpress.", "temu.com", "reddit.com",
                "quora.com", "linkedin.com", "play.google.com", "apps.apple.com")
SOCIAL = {"facebook": "facebook.com", "instagram": "instagram.com", "linkedin": "linkedin.com"}


def skip(url: str) -> bool:
    d = url_domain(url) or ""
    return any(s in d for s in SKIP_DOMAINS) or url.lower().endswith((".pdf", ".jpg", ".png", ".zip"))


def search(query: str, pageno: int = 1) -> list[dict]:
    """[{url, title, content}] from SearXNG."""
    try:
        r = httpx.get(f"{SEARXNG_URL}/search", params={"q": query, "format": "json", "pageno": pageno}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    out = []
    for res in r.json().get("results", []):
        if res.get("url"):
            out.append({"url": res["url"], "title": res.get("title") or "", "content": res.get("content") or ""})
    return out


def _plain_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, limit: int = 12000) -> tuple[str | None, str | None]:
    """(html, readable text). Falls back to plain text when the article extractor finds nothing."""
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True, headers=HEADERS)
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return None, None
        html = r.text
    except httpx.HTTPError:
        return None, None
    text = trafilatura.extract(html, include_tables=True, include_links=False, favor_recall=True)
    if not text or len(text) < 300:
        plain = _plain_text(html)
        if len(plain) > len(text or ""):
            text = plain
    return html, (text[:limit] if text else None)


LINK_WORDS = ("about", "contact", "company", "profile", "who-we-are", "products", "factory")


def inner_links(base_url: str, html: str, max_links: int = 3) -> list[str]:
    """About / Contact style pages on the same site."""
    host = url_domain(base_url)
    found = []
    for href in re.findall(r'href=["\']([^"\'#]+)', html or "", re.I):
        full = urljoin(base_url, href)
        if url_domain(full) != host or full.rstrip("/") == base_url.rstrip("/"):
            continue
        path = urlparse(full).path.lower()
        if any(w in path for w in LINK_WORDS) and full not in found:
            found.append(full)
        if len(found) >= max_links:
            break
    return found


def social_kind(url: str) -> str | None:
    d = url_domain(url) or ""
    for kind, host in SOCIAL.items():
        if d.endswith(host):
            return kind
    return None
