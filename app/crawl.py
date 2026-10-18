"""The crawler: search (SearXNG), download pages politely, render JavaScript pages, cache, follow links.

Everything here is plain code. The AI only sees the text this module returns.
"""
import gzip
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
import trafilatura

from .db import PageCache, SessionLocal, get_setting, url_domain

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")
RENDER_URL = os.environ.get("RENDER_URL", "http://renderer:3000")
UA = "Mozilla/5.0 (compatible; NetGate/0.5; business directory research)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en;q=0.9,*;q=0.5"}

CRAWLER_DEFAULTS = {
    "render": "auto",          # auto / never / always
    "render_domains": "",      # sites that always need the browser, one per line
    "next_pages": 4,           # extra "next" pages followed per list page
    "directory_mode": True,    # open company profile links found on list pages
    "profiles_per_page": 15,
    "site_pages": 8,           # pages of a company's own website read by Enrich
    "cache_days": 3,
    "delay": 2.0,              # seconds between two requests to the same website
    "robots": True,            # follow robots.txt
    "max_chunks": 3,           # long pages are split into this many parts at most
    "skip_domains": "",        # extra sites to never read, one per line
}

# Sites that never help: videos, images, shops and social sites that need a login to read.
SKIP_DOMAINS = ("youtube.com", "youtu.be", "pinterest.", "tiktok.com", "facebook.com", "instagram.com",
                "x.com", "twitter.com", "amazon.", "ebay.", "aliexpress.", "temu.com", "reddit.com",
                "quora.com", "linkedin.com", "play.google.com", "apps.apple.com", "wikipedia.org")
SOCIAL = {"facebook": "facebook.com", "instagram": "instagram.com", "linkedin": "linkedin.com"}
FILE_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".rar", ".mp4", ".doc", ".docx",
            ".xls", ".xlsx", ".ppt", ".pptx", ".svg")


# ---------- settings ----------

_settings_cache: dict = {"at": 0.0, "value": None}


def settings() -> dict:
    """Crawler settings from Settings → Crawler (re-read at most once a minute)."""
    if _settings_cache["value"] is None or time.time() - _settings_cache["at"] > 60:
        try:
            with SessionLocal() as s:
                saved = get_setting(s, "crawler", {}) or {}
        except Exception:
            saved = {}
        _settings_cache.update(at=time.time(), value={**CRAWLER_DEFAULTS, **saved})
    return _settings_cache["value"]


def _lines(value: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[\n,]+", value or "") if x.strip()]


def skip(url: str) -> bool:
    d = url_domain(url) or ""
    extra = tuple(_lines(settings().get("skip_domains", "")))
    path = urlparse(url).path.lower()
    return any(s in d for s in SKIP_DOMAINS + extra) or path.endswith(FILE_EXT)


def social_kind(url: str) -> str | None:
    d = url_domain(url) or ""
    for kind, host in SOCIAL.items():
        if d == host or d.endswith("." + host):
            return kind
    return None


# ---------- search ----------

_search_ctx = threading.local()
last_search = threading.local()   # .errors: engines that failed in this thread's last search (for Debug)


def set_search_job(job_id: int | None):
    """Searches made from now on in this worker belong to this request (Settings → Search Engines log)."""
    _search_ctx.job_id = job_id


def search(query: str, pageno: int = 1, engines: list[str] | None = None, test: bool = False) -> list[dict]:
    """[{url, title, content, engines}] from SearXNG, with the engines chosen in Settings → Search Engines
    (or `engines` given here, e.g. by Test Now). Every search is logged: links per engine and failed engines."""
    from . import engines as EN
    use = engines or EN.chosen()
    params = {"q": query, "format": "json", "pageno": pageno}
    if use:
        params["engines"] = ",".join(use)
    last_search.errors = {}
    job_id = getattr(_search_ctx, "job_id", None)
    try:
        r = httpx.get(f"{SEARXNG_URL}/search", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        last_search.errors = {"searxng": f"search engine not reachable ({type(e).__name__})"}
        EN.record(query, pageno, use, {}, last_search.errors, job_id, test)
        return []
    out, counts = [], {}
    for res in data.get("results", []):
        if res.get("url"):
            engs = [str(x) for x in (res.get("engines") or ([res["engine"]] if res.get("engine") else []))]
            for e in engs:
                counts[e] = counts.get(e, 0) + 1
            out.append({"url": res["url"], "title": res.get("title") or "", "content": res.get("content") or "",
                        "engines": engs})
    errors = {}
    for item in data.get("unresponsive_engines") or []:
        if isinstance(item, (list, tuple)) and item:
            errors[str(item[0])] = str(item[1] if len(item) > 1 else "no answer")
    last_search.errors = errors
    EN.record(query, pageno, use, counts, errors, job_id, test)
    return out


# ---------- politeness ----------

_redis = None
_robots: dict[str, tuple[float, RobotFileParser | None]] = {}


def _redis_client():
    global _redis
    if _redis is None:
        try:
            from redis import Redis
            _redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
        except Exception:
            _redis = False
    return _redis or None


def wait_turn(host: str):
    """Leave `delay` seconds between requests to the same site, across all workers."""
    delay = float(settings().get("delay") or 0)
    if not delay or not host:
        return
    r = _redis_client()
    if not r:
        return
    try:
        for _ in range(int(delay * 4) + 40):
            if r.set(f"netgate:host:{host}", "1", px=int(delay * 1000), nx=True):
                return
            time.sleep(0.25)
    except Exception:
        return  # Redis trouble should never stop a crawl


def robots_allowed(url: str) -> bool:
    if not settings().get("robots", True):
        return True
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    cached = _robots.get(base)
    if not cached or time.time() - cached[0] > 86400:
        parser = None
        try:
            r = httpx.get(base + "/robots.txt", timeout=10, headers=HEADERS, follow_redirects=True)
            if r.status_code == 200 and "text" in r.headers.get("content-type", "text"):
                parser = RobotFileParser()
                parser.parse(r.text.splitlines())
        except httpx.HTTPError:
            parser = None
        _robots[base] = cached = (time.time(), parser)
    parser = cached[1]
    return True if parser is None else parser.can_fetch("NetGate", url)


# ---------- download & render (small functions so tests can replace them) ----------

def _http_get(url: str) -> tuple[int, str, str, str]:
    """(status, final_url, content_type, body). One retry on timeouts and server errors."""
    last = (0, url, "", "")
    for attempt in range(2):
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True, headers=HEADERS)
            last = (r.status_code, str(r.url), r.headers.get("content-type", ""), r.text)
            if r.status_code < 500:
                return last
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
            pass
        except httpx.HTTPError:
            return last
        time.sleep(2 * (attempt + 1))
    return last


def _render(url: str) -> str | None:
    try:
        r = httpx.get(f"{RENDER_URL}/render", params={"url": url, "wait": 1000}, timeout=60)
        return r.text if r.status_code == 200 and r.text else None
    except httpx.HTTPError:
        return None


# ---------- text ----------

def plain_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|template).*?</\1>", " ", html or "")
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td|section|article)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text).replace("&amp;", "&")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def readable_text(html: str) -> str:
    """Main text of a page; falls back to all visible text for list pages the extractor drops."""
    main = trafilatura.extract(html, include_tables=True, include_links=False, favor_recall=True) or ""
    plain = plain_text(html)
    # list / directory pages: the article extractor often keeps only a small part
    return plain if len(plain) > max(1.6 * len(main), len(main) + 1500) else (main or plain)


def needs_render(html: str, text: str, url: str) -> bool:
    mode = settings().get("render", "auto")
    if mode == "never":
        return False
    if mode == "always":
        return True
    d = url_domain(url) or ""
    if any(d == x or d.endswith("." + x) for x in _lines(settings().get("render_domains", ""))):
        return True
    low = (html or "").lower()
    if "enable javascript" in low or "requires javascript" in low or "javascript is disabled" in low:
        return True
    return len(text or "") < 400 and low.count("<script") >= 2


def chunks(text: str, size: int = 10000, overlap: int = 400, limit: int | None = None) -> list[str]:
    limit = limit or int(settings().get("max_chunks") or 3)
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text) and len(out) < limit:
        out.append(text[start:start + size])
        start += size - overlap
    return out


# ---------- pages ----------

@dataclass
class Page:
    url: str
    final_url: str = ""
    html: str = ""
    text: str = ""
    ok: bool = False
    rendered: bool = False
    cached: bool = False
    note: str = ""
    links: list = field(default_factory=list)


def _from_cache(url: str, days: int) -> Page | None:
    if not days:
        return None
    try:
        with SessionLocal() as s:
            row = s.get(PageCache, url)
            if not row or datetime.utcnow() - row.fetched_at > timedelta(days=days):
                return None
            html = gzip.decompress(row.html_gz).decode("utf-8", "replace") if row.html_gz else ""
            return Page(url=url, final_url=row.final_url or url, html=html, text=row.text or "",
                        ok=bool(row.status and row.text), rendered=row.rendered, cached=True)
    except Exception:
        return None


def _to_cache(page: Page, status: int):
    try:
        with SessionLocal() as s:
            row = s.get(PageCache, page.url) or PageCache(url=page.url)
            row.final_url, row.status, row.rendered = page.final_url, status if page.ok else 0, page.rendered
            row.text = page.text[:300000] if page.text else None
            row.html_gz = gzip.compress(page.html.encode("utf-8", "replace")[:3_000_000]) if page.html else None
            row.fetched_at = datetime.utcnow()
            s.merge(row)
            s.commit()
    except Exception:
        pass


def get_page(url: str, use_cache: bool = True) -> Page:
    """Download a page (from cache when fresh), render it in the browser when needed, return its text."""
    cfg = settings()
    if use_cache:
        hit = _from_cache(url, int(cfg.get("cache_days") or 0))
        if hit:
            return hit
    page = Page(url=url, final_url=url)
    if not robots_allowed(url):
        page.note = "blocked by robots.txt"
        return page
    host = url_domain(url) or ""
    wait_turn(host)
    status, final_url, ctype, body = _http_get(url)
    page.final_url = final_url or url
    if status and status < 400 and ("html" in ctype or not ctype):
        page.html = body
        page.text = readable_text(body)
    if needs_render(page.html, page.text, url) or (status in (401, 403, 429) and cfg.get("render") != "never"):
        html = _render(url)
        if html:
            text = readable_text(html)
            if len(text) > len(page.text):
                page.html, page.text, page.rendered = html, text, True
                status = status if status and status < 400 else 200
    page.ok = bool(page.text and len(page.text.strip()) >= 20)   # short profile pages still count
    if not page.ok:
        page.note = page.note or (f"HTTP {status}" if status else "could not download")
    _to_cache(page, status)
    return page


def fetch(url: str, limit: int = 12000) -> tuple[str | None, str | None]:
    """Older helper kept for callers that only need (html, text)."""
    p = get_page(url)
    return (p.html or None, p.text[:limit] if p.ok else None)


# ---------- links ----------

_A = re.compile(r"<a\b[^>]*?href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", re.I | re.S)


def links(html: str, base: str) -> list[tuple[str, str]]:
    """[(absolute_url, anchor_text)] in page order, without duplicates."""
    out, seen = [], set()
    for _, href, inner in _A.findall(html or ""):
        href = href.strip().replace("&amp;", "&")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:", "data:")):
            continue
        full = urljoin(base, href).split("#")[0]
        if full in seen:
            continue
        seen.add(full)
        text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", inner)).strip()
        out.append((full, text))
    return out


NEXT_WORDS = re.compile(r"^(next|next page|weiter|nächste|suivant|siguiente|successivo|avanti|›|»|>|→|>>)$", re.I)


def next_page_url(html: str, base: str) -> str | None:
    """The 'next page' link of a list page, if there is one."""
    m = re.search(r"<(?:link|a)\b[^>]*rel\s*=\s*[\"']next[\"'][^>]*href\s*=\s*[\"']([^\"']+)", html or "", re.I) \
        or re.search(r"<(?:link|a)\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*rel\s*=\s*[\"']next[\"']", html or "", re.I)
    if m:
        return urljoin(base, m.group(1).replace("&amp;", "&"))
    host = url_domain(base)
    for url, text in links(html, base):
        label = text.strip().lower()
        if url_domain(url) == host and (NEXT_WORDS.match(label) or label in ("next »", "next ›", "next >")):
            return url
    # page=2 → page=3 style links
    cur = re.search(r"([?&](?:page|p|pg|pageno)=)(\d+)", base)
    n = int(cur.group(2)) if cur else 1
    for url, _ in links(html, base):
        if url_domain(url) != host:
            continue
        m2 = re.search(r"[?&](?:page|p|pg|pageno)=(\d+)", url) or re.search(r"/page/(\d+)/?$", url)
        if m2 and int(m2.group(1)) == n + 1:
            return url
    return None


SITE_WORDS = ("contact", "about", "impressum", "imprint", "kontakt", "company", "profile", "who-we-are",
              "products", "factory", "our-story", "team", "chi-siamo", "qui-sommes", "mentions-legales",
              "contatti", "legal-notice", "legal")


def _score(url: str) -> int:
    path = urlparse(url).path.lower()
    for i, w in enumerate(SITE_WORDS):
        if w in path:
            return i
    return 99


def sitemap_urls(site_url: str, limit: int = 200) -> list[str]:
    parts = urlparse(site_url if "://" in site_url else "https://" + site_url)
    base = f"{parts.scheme}://{parts.netloc}"
    found: list[str] = []
    for sm in (base + "/sitemap.xml", base + "/sitemap_index.xml"):
        if len(found) >= limit:
            break
        status, _, _, body = _http_get(sm)
        if status != 200 or "<" not in (body or ""):
            continue
        try:
            root = ElementTree.fromstring(body.encode("utf-8", "replace"))
        except ElementTree.ParseError:
            continue
        locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
        subs = [u for u in locs if u.endswith(".xml")][:3]
        found += [u for u in locs if not u.endswith(".xml")]
        for sub in subs:
            s2, _, _, b2 = _http_get(sub)
            if s2 == 200:
                try:
                    r2 = ElementTree.fromstring(b2.encode("utf-8", "replace"))
                    found += [el.text.strip() for el in r2.iter() if el.tag.endswith("loc") and el.text]
                except ElementTree.ParseError:
                    pass
        if found:
            break
    return found[:limit]


def site_pages(home: Page, limit: int) -> list[str]:
    """The most useful pages of a company's own site: contact, about, imprint, products…"""
    host = url_domain(home.final_url or home.url)
    cand = [u for u, _ in links(home.html, home.final_url or home.url) if url_domain(u) == host]
    try:
        cand += [u for u in sitemap_urls(home.final_url or home.url) if url_domain(u) == host]
    except Exception:
        pass
    seen, out = {home.url.rstrip("/"), (home.final_url or "").rstrip("/")}, []
    for u in sorted(cand, key=_score):
        key = u.rstrip("/")
        if key in seen or _score(u) == 99 or skip(u):
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def inner_links(base_url: str, html: str, max_links: int = 3) -> list[str]:
    """Older helper: About / Contact style pages on the same site."""
    host = url_domain(base_url)
    out = []
    for u, _ in links(html, base_url):
        if url_domain(u) == host and _score(u) < 99 and u.rstrip("/") != base_url.rstrip("/") and u not in out:
            out.append(u)
        if len(out) >= max_links:
            break
    return out


def renderer_status() -> bool:
    try:
        return httpx.get(f"{RENDER_URL}/health", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def purge_cache(days: int | None = None) -> int:
    days = days if days is not None else int(settings().get("cache_days") or 3)
    cutoff = datetime.utcnow() - timedelta(days=days) if days else datetime.utcnow() + timedelta(days=1)
    with SessionLocal() as s:
        n = s.query(PageCache).filter(PageCache.fetched_at < cutoff).delete()
        s.commit()
    return n
