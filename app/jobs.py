"""Background jobs: Discover (find companies with a directory's search methods), Enrich (fill missing fields)
and the night batch. New companies go to the Inbox; nothing reaches a directory until someone accepts it.

Every job checks for Pause / Stop between pages (see control.py) and writes a debug trace (Developer tools).
"""
import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import ai, contacts, control, crawl, ebay, extract, learn, methods
from .db import (DISCOVER_KEYS, Group, InboxItem, Job, JobTrace, Keyword, Membership, NightRun, Record,
                 SessionLocal, User, get_setting, log, name_key, url_domain)

MAX_PAGES = int(os.environ.get("MAX_PAGES", 15))        # search-result pages read per Discover
ENRICH_PAGES = int(os.environ.get("ENRICH_PAGES", 6))   # other pages (not the company's own site) per Enrich
TRACE_LIMIT = 400                                       # debug rows kept per job

NIGHT_DEFAULTS = {"enabled": False, "start": "23:00", "stop": "07:00", "days": [0, 1, 2, 3, 4, 5],
                  "max_companies": 150, "pause": 3, "timezone": "Asia/Karachi", "enrich_inbox": True}

TYPE_HINTS = {
    "text": "short text, or null",
    "list": "list of short strings, or []",
    "number": "a number, or null",
    "email": "an email address, or null",
    "url": "a website address, or null",
    "phone": "a phone number with country code if shown, or null",
}


class Paused(Exception):
    pass


class Stopped(Exception):
    pass


# ---------- small helpers ----------

def empty(v) -> bool:
    return v in (None, "", [], "Unknown")


def completeness(record, group) -> tuple[int, int]:
    fields = group.fields if group else []
    data = record.data or {}
    filled = sum(1 for f in fields if not empty(data.get(f.key)))
    return filled, len(fields)


def field_line(f) -> str:
    if f.type == "choice":
        options = ", ".join(f'"{c}"' for c in f.choice_list())
        hint = f'exactly one of {options}, or "Unknown"'
    else:
        hint = TYPE_HINTS.get(f.type, TYPE_HINTS["text"])
    return f'    "{f.key}": {f.name} - {hint}'


def clean(f, value):
    """Make a value from the model fit the field type."""
    if f.type == "list":
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",")]
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip() and str(v).strip().lower() != "null"][:15]
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or str(value).strip().lower() in ("", "null", "none", "n/a", "unknown", "not stated"):
        return "Unknown" if f.type == "choice" else None
    value = str(value).strip()
    if f.type == "choice":
        return value if value in f.choice_list() else "Unknown"
    if f.type == "number":
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    if f.type == "url":
        if " " in value or "." not in value:
            return None
        return value if value.startswith("http") else "https://" + value.lstrip("/")
    if f.type == "email" and "@" not in value:
        return None
    return value[:300]


def name_tokens(name: str) -> list[str]:
    return [t for t in name_key(name).split() if len(t) >= 3]


def mentions(text: str, tokens: list[str]) -> bool:
    if not tokens:
        return True
    low = (text or "").lower()
    hits = sum(1 for t in tokens if t in low)
    return hits >= max(1, math.ceil(len(tokens) * 0.6))


def homepage(url: str) -> str:
    p = re.match(r"(https?://[^/]+)", url or "")
    return (p.group(1) + "/") if p else url


def searchable(f) -> bool:
    """Fields the crawler and AI look for (not manual-only, not filled by a marketplace API)."""
    return f.source in ("", "website")


class Ctx:
    """Progress, counters, pause/stop checks and the debug trace of one job."""

    def __init__(self, job_id: int | None, ai_type: str, stop_rule=None, pause: float = 0.0, user: str = ""):
        self.job_id, self.ai_type, self.stop_rule, self.pause, self.user = job_id, ai_type, stop_rule, pause, user
        self.stats = {"results": 0, "read": 0, "failed": 0, "saved": 0, "updated": 0, "fields": 0,
                      "rendered": 0, "cached": 0, "next_pages": 0, "profiles": 0, "page_no": 0, "pages_total": 0}
        self.state: dict = {}          # saved when paused, given back on Resume
        self.resume_state: dict = {}
        self.notes: list[str] = []
        self.new_items: list[int] = []
        self._control, self._checked, self._traces = "", 0.0, 0
        try:
            with SessionLocal() as s:
                self.tracing = bool((get_setting(s, "dev", {}) or {}).get("trace", True)) and job_id is not None
        except Exception:
            self.tracing = False

    def step(self, status: str, message: str):
        if self.job_id is None:   # a test run from Settings: nothing to record
            return
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job:
                self._control, self._checked = job.control or "", time.time()
                job.status = {"pause": "pausing", "stop": "stopping"}.get(self._control, status)
                job.message, job.stats = message[:500], dict(self.stats)
                job.saved, job.updated = self.stats["saved"], self.stats["updated"]
                s.commit()

    def check(self):
        """Raise Paused / Stopped when the user asked for it (read from the database every 2 s at most)."""
        if self.job_id is None:
            return
        if time.time() - self._checked > 2:
            with SessionLocal() as s:
                job = s.get(Job, self.job_id)
                self._control = (job.control if job else "stop") or ""
                self._checked = time.time()
        if self._control == "pause":
            raise Paused()
        if self._control == "stop":
            raise Stopped()

    def should_stop(self) -> bool:
        self.check()
        return bool(self.stop_rule and self.stop_rule())

    def wait(self):
        if self.pause:
            time.sleep(self.pause)

    def count_page(self, page) -> bool:
        self.trace("page", page.final_url or page.url, ok=page.ok, rendered=page.rendered, cached=page.cached,
                   note=page.note, chars=len(page.text or ""), text=(page.text or "")[:3000])
        if not page.ok:
            self.stats["failed"] += 1
            return False
        self.stats["read"] += 1
        self.stats["rendered"] += int(page.rendered)
        self.stats["cached"] += int(page.cached)
        return True

    def trace(self, kind: str, url: str = "", **data):
        if not self.tracing or self._traces >= TRACE_LIMIT:
            return
        self._traces += 1

        def cut(v):
            if isinstance(v, str):
                return v[:4000]
            if isinstance(v, dict):
                return {k: cut(x) for k, x in list(v.items())[:60]}
            if isinstance(v, list):
                return [cut(x) for x in v[:60]]
            return v
        try:
            with SessionLocal() as s:
                s.add(JobTrace(job_id=self.job_id, kind=kind[:20], url=(url or "")[:2000],
                               data=json.loads(json.dumps(cut(data), default=str))))
                s.commit()
        except Exception:
            pass

    def history(self, method: str, query: str) -> str:
        label = contacts.METHOD_LABELS.get(method, method)
        return f"Found by {label} “{query[:80]}” · {datetime.utcnow():%d %b %Y}" + (f" · {self.user}" if self.user else "")


def ask(ctx: Ctx, prompt: str, url: str = ""):
    data = ai.ask_json(ctx.ai_type, prompt)
    ctx.trace("ai", url, prompt=prompt[:2500] + ("\n…\n" + prompt[-800:] if len(prompt) > 3300 else ""),
              answer=data)
    return data


# ---------- saving what was found ----------

def save_found(s, ctx: Ctx, group, *, name: str, values: dict, sources: dict, method: str, query: str,
               page_url: str, summary: str = "", social: dict | None = None, links: dict | None = None,
               ext: dict | None = None) -> str | None:
    """Add or update the contact, then put it in the Inbox for this directory. Returns 'saved', 'updated' or None."""
    name = (name or "").strip()
    if len(name) < 2 or len(name) > 150:
        return None
    rec, created, changed = contacts.upsert(
        s, name=name, values=values, sources=sources, social=social, links=links, ext=ext, summary=summary,
        source_url=page_url, topic=query, job_id=ctx.job_id, history=ctx.history(method, query))
    item = contacts.to_inbox(s, rec, group.id, method=method, keyword=query, job_id=ctx.job_id, found_url=page_url)
    if item:
        if not created:
            contacts.add_history(rec, ctx.history(method, query) + f" for {group.name}")
        ctx.new_items.append(item.id)
        return "saved"
    return "updated" if changed and not created else None


def entry_values(group, entry: dict, page_url: str):
    by_key = {f.key: f for f in group.fields if searchable(f)}
    raw = dict(entry.get("fields") or {}) if isinstance(entry.get("fields"), dict) else {}
    for k in DISCOVER_KEYS:
        if entry.get(k) not in (None, ""):
            raw.setdefault(k, entry.get(k))
    values, sources = {}, {}
    for key, value in raw.items():
        f = by_key.get(key)
        if f:
            v = clean(f, value)
            if not empty(v):
                values[key], sources[key] = v, page_url
    found, found_url = entry.get("_found"), entry.get("_found_url") or page_url
    if found:   # code-found email / phone / address from the company's page or directory profile
        for k, v in extract.fill_fields([f for f in group.fields if searchable(f)], found, values,
                                        values.get("website")).items():
            values[k], sources[k] = v, found_url
    social = dict((found or {}).get("social") or {}) if entry.get("_own_site") else {}
    return values, sources, social


def save_entry(s, ctx: Ctx, group, entry: dict, page_url: str, query: str, method: str = "web") -> str | None:
    values, sources, social = entry_values(group, entry, page_url)
    return save_found(s, ctx, group, name=str(entry.get("name") or ""), values=values, sources=sources,
                      method=method, query=query, page_url=page_url, summary=str(entry.get("description") or ""),
                      social=social)


def _score_new(ctx: Ctx):
    if not ctx.new_items:
        return
    try:
        with SessionLocal() as s:
            items = s.scalars(select(InboxItem).where(InboxItem.id.in_(ctx.new_items))).all()
            learn.score_items(s, items)
            s.commit()
    except Exception as e:
        log("warning", "learn", f"Could not score new Inbox items: {type(e).__name__}: {e}")
    ctx.new_items = []


# ---------- Discover: reading pages ----------

DISCOVER_PROMPT = """You collect companies for the "{group}" section of a business directory.
What belongs in this section: {instructions}
Skip: {ignore}
The user is looking for: {query}

Page address: {url}{part}
Page text:
{text}

List every {group} entry on this page that matches what the user is looking for. The page may describe one company, or be a list or directory of many.
Return JSON only, in this shape:
{{"entries": [{{"name": "...", "city": "...", "country": "...", "website": "...", "description": "1-2 sentences", "fields": {{...}}}}]}}
Rules:
- Use null when the page does not say. Never invent values.
- "website" is the company's own website if the page shows it, otherwise null.
- Leave out news, adverts, job posts and anything in the Skip list.
- At most 40 entries. Return {{"entries": []}} if nothing matches.
Keys for "fields":
{fields}"""


def discover_queries(text: str, group) -> list[tuple[str, int]]:
    base = f"{text} {group.search_terms}".strip()
    return [(base, 1), (f"{base} list", 1), (f"top {base} companies", 1), (base, 2)]


def _ask_entries(ctx: Ctx, group, query: str, page) -> list[dict]:
    discover_fields = [f for f in group.fields if f.stage == "discover" and f.key not in DISCOVER_KEYS
                       and searchable(f)]
    parts = crawl.chunks(page.text)
    entries, seen = [], set()
    for n, part in enumerate(parts, 1):
        prompt = DISCOVER_PROMPT.format(
            group=group.name, instructions=group.instructions or "-", ignore=group.ignore_instructions or "-",
            query=query, url=page.final_url or page.url,
            part=f" (part {n} of {len(parts)})" if len(parts) > 1 else "", text=part,
            fields="\n".join(field_line(f) for f in discover_fields) or "    (none)")
        try:
            data = ask(ctx, prompt, page.final_url or page.url)
        except Exception as e:  # one bad page should not stop the whole job
            ctx.stats["failed"] += 1
            ctx.trace("error", page.final_url or page.url, error=f"AI error: {type(e).__name__}: {e}")
            ctx.step("extracting", f"AI error: {type(e).__name__}")
            continue
        for e in (data or {}).get("entries") or []:
            if isinstance(e, dict) and e.get("name"):
                k = name_key(str(e["name"]))
                if k and k not in seen:
                    seen.add(k)
                    entries.append(e)
    return entries[:60]


def _entry_link(page, name: str) -> str | None:
    """The link on a list page whose text is this company's name."""
    tokens = name_tokens(name)
    low_name = name.lower().strip()
    for url, label in page.links:
        lab = label.lower()
        if not lab or len(lab) > 160:
            continue
        if low_name in lab or (len(tokens) >= 2 and all(t in lab for t in tokens)):
            return url
    return None


def _enhance_entries(ctx: Ctx, page, entries: list[dict], directory_mode: bool | None = None):
    """Code-first details: the company's own page, or the profile pages a directory links to."""
    cfg = crawl.settings()
    page.links = crawl.links(page.html, page.final_url or page.url)
    host = url_domain(page.final_url or page.url)
    if len(entries) == 1:
        e = entries[0]
        tokens = name_tokens(e["name"])
        if not e.get("website") and host and any(t in host for t in tokens):
            e["website"] = homepage(page.final_url or page.url)   # this is the company's own site
        e["_found"] = extract.analyze(page.html, page.text, page.final_url or page.url)
        e["_own_site"] = bool(host and any(t in host for t in tokens))
        ctx.trace("code", page.final_url or page.url, company=e["name"], found=e["_found"])
        return
    if not (cfg.get("directory_mode", True) if directory_mode is None else directory_mode):
        return
    budget = int(cfg.get("profiles_per_page") or 0)
    for e in entries:
        link = _entry_link(page, e["name"])
        if not link or crawl.skip(link):
            continue
        if url_domain(link) != host:
            e.setdefault("website", None)
            if not e.get("website") and not crawl.social_kind(link):
                e["website"] = homepage(link)
            continue
        if budget <= 0 or ctx.should_stop():
            continue
        budget -= 1
        ctx.step("crawling", f"Profile of {e['name']}: {link}")
        prof = crawl.get_page(link)
        ctx.stats["profiles"] += 1
        if not ctx.count_page(prof):
            continue
        site = extract.external_website(prof.html, prof.final_url or link, e["name"])
        if site and not e.get("website"):
            e["website"] = homepage(site)
        e["_found"] = extract.analyze(prof.html, prof.text, prof.final_url or link)
        e["_found_url"] = prof.final_url or link
        ctx.trace("code", prof.final_url or link, company=e["name"], website=e.get("website"), found=e["_found"])


def crawl_pages(ctx: Ctx, group_id: int, query: str, method: str, queue: list, seen: set, done: int,
                directory_mode: bool | None = None):
    """Read queued pages; list pages add their next page to the front of the queue."""
    max_next = int(crawl.settings().get("next_pages") or 0)
    with SessionLocal() as s:
        group = s.get(Group, group_id)
        _ = group.fields
    while queue:
        if ctx.should_stop():
            break
        url, depth = queue.pop(0)
        try:
            done += 1
            ctx.stats["page_no"], ctx.stats["pages_total"] = done, done + len(queue)
            label = f"Page {done} of {done + len(queue)}" + (f" (next page {depth})" if depth else "")
            ctx.step("crawling", f"{label}: {url}")
            page = crawl.get_page(url)
            if not ctx.count_page(page):
                continue
            ctx.step("extracting", f"{label}: {url}")
            entries = _ask_entries(ctx, group, query, page)
            if entries:
                _enhance_entries(ctx, page, entries, directory_mode)
            if len(entries) >= 3 and depth < max_next:
                nxt = crawl.next_page_url(page.html, page.final_url or url)
                if nxt and nxt not in seen:
                    seen.add(nxt)
                    queue.insert(0, (nxt, depth + 1))   # finish this list before moving on
                    ctx.stats["next_pages"] += 1
            with SessionLocal() as s:
                group = s.get(Group, group_id)
                for entry in entries:
                    result = save_entry(s, ctx, group, entry, page.final_url or url, query, method)
                    if result:
                        ctx.stats[result] += 1
                    s.flush()
                s.commit()
            _score_new(ctx)
        except Paused:
            queue.insert(0, (url, depth))   # read this page again after Resume
            ctx.state[method] = {"queue": queue, "seen": sorted(seen), "done": done - 1}
            raise
        ctx.wait()
    return done


def web_discover(ctx: Ctx, group, query: str, sub: dict | None):
    if sub:
        queue, seen, done = [tuple(x) for x in sub.get("queue", [])], set(sub.get("seen", [])), int(sub.get("done", 0))
    else:
        seen, queue, done = set(), [], 0
        for q, pageno in discover_queries(query, group):
            if len(queue) >= MAX_PAGES or ctx.should_stop():
                break
            ctx.step("searching", f"Searching: {q}" + (" (page 2)" if pageno > 1 else ""))
            results = crawl.search(q, pageno)
            ctx.trace("search", q, page=pageno, results=[r["url"] for r in results])
            for res in results:
                ctx.stats["results"] += 1
                u = res["url"]
                if u not in seen and not crawl.skip(u):
                    seen.add(u)
                    queue.append((u, 0))
        queue = queue[:MAX_PAGES]
    crawl_pages(ctx, group.id, query, "web", queue, seen, done)


def directory_discover(ctx: Ctx, group, query: str, sub: dict | None):
    """Directory sites: given list pages (a {q} in the address is replaced by the keyword) and/or sites
    searched with site:…, read with profiles and next pages always on."""
    from urllib.parse import quote_plus
    opts = methods.options(group, "directory")
    if sub:
        queue, seen, done = [tuple(x) for x in sub.get("queue", [])], set(sub.get("seen", [])), int(sub.get("done", 0))
    else:
        seen, queue, done = set(), [], 0
        for line in crawl._lines(opts.get("start_urls") or ""):
            u = line.replace("{q}", quote_plus(query))
            if u.startswith("http") and u not in seen:
                seen.add(u)
                queue.append((u, 0))
        for site in crawl._lines(opts.get("sites") or ""):
            site = site.replace("https://", "").replace("http://", "").strip("/")
            q = f"{query} site:{site}"
            ctx.step("searching", f"Searching: {q}")
            results = crawl.search(q)
            ctx.trace("search", q, results=[r["url"] for r in results])
            for res in results[:8]:
                ctx.stats["results"] += 1
                if res["url"] not in seen:
                    seen.add(res["url"])
                    queue.append((res["url"], 0))
        if not queue:
            ctx.notes.append("Directory site search has no list pages or sites set up (Directory settings).")
            return
    crawl_pages(ctx, group.id, query, "directory", queue[:MAX_PAGES * 2], seen, done, directory_mode=True)


def ebay_discover(ctx: Ctx, group, query: str):
    with SessionLocal() as s:
        conn = methods.connections(s)
    if not ebay.ready(conn):
        ctx.notes.append("eBay keys are not set up yet (Settings → Connections), so eBay search was skipped.")
        return
    opts = methods.options(group, "ebay")
    ctx.step("searching", f"eBay: searching “{query}”")
    for info in ebay.find_sellers(conn, opts, query, check=ctx.check, note=ctx.trace):
        if ctx.should_stop():
            break
        ctx.stats["results"] += 1
        with SessionLocal() as s:
            g = s.get(Group, group.id)
            values = ebay.values_for(g.fields, info)
            sources = {k: info["store_url"] for k in values}
            name = info.get("business_name") or info["username"]
            summary = (f"eBay seller on {', '.join(info.get('sites') or [])}"
                       + (f" · {info['feedback_pct']} positive" if info.get("feedback_pct") else "")
                       + (f" · {info['feedback_score']} ratings" if info.get("feedback_score") else "")
                       + (f" · sells: {'; '.join(info.get('products', [])[:3])}" if info.get("products") else ""))
            result = save_found(s, ctx, g, name=name, values=values, sources=sources, method="ebay", query=query,
                                page_url=info["store_url"], summary=summary, links={"ebay": info["store_url"]},
                                ext={"ebay": info["username"].lower()})
            if result:
                ctx.stats[result] += 1
            s.commit()
        ctx.step("extracting", f"eBay: {info['username']} ({ctx.stats['saved']} new)")
    _score_new(ctx)


def discover(ctx: Ctx, group_id: int, query: str, use_methods: list[str] | None = None):
    with SessionLocal() as s:
        group = s.get(Group, group_id)
        _ = group.fields
    use = [m for m in (use_methods or methods.enabled_find_methods(group)) if m in methods.FIND_METHODS]
    state = ctx.resume_state or {}
    done_methods = list(state.get("done_methods") or [])
    for m in use:
        if m in done_methods:
            continue
        ctx.state = {"done_methods": done_methods, "current": m}
        sub = state.get(m) if state.get("current") == m else None
        try:
            if m == "web":
                web_discover(ctx, group, query, sub)
            elif m == "directory":
                directory_discover(ctx, group, query, sub)
            elif m == "ebay":
                ebay_discover(ctx, group, query)
        except ebay.EbayError as e:
            ctx.notes.append(str(e))
            ctx.trace("error", "", error=str(e))
        done_methods.append(m)
        if ctx.should_stop():
            break
    return ctx.stats


# ---------- Enrich ----------

ENRICH_PROMPT = """You are filling in missing details about ONE company for the "{group}" section of a business directory.
Company: {name} ({place})
Already known: {known}
Guidance: {guidance}

Source: {source}
Text:
{text}

Only use information that is clearly about this company. If the text is about a different company, return {{"same_company": false}}.
Return JSON only, in this shape:
{{"same_company": true, "description": "2-3 sentences about the company, or null", "fields": {{...}}}}
Use null for anything the text does not say. Never guess.
Keys for "fields":
{fields}"""


def _ask_enrich(ctx, group_name, guidance, rec_info, missing, source, text):
    prompt = ENRICH_PROMPT.format(
        group=group_name, name=rec_info["name"], place=rec_info["place"] or "location unknown",
        known=json.dumps(rec_info["known"], ensure_ascii=False)[:1500],
        guidance=guidance or "Prefer the company's own website.",
        source=source, text=text, fields="\n".join(field_line(f) for f in missing))
    try:
        return ask(ctx, prompt, source)
    except Exception as e:
        ctx.stats["failed"] += 1
        ctx.trace("error", source, error=f"AI error: {type(e).__name__}: {e}")
        return None


def enrich(ctx: Ctx, record_id: int, refresh: bool = False, steps: list[str] | None = None) -> list[str]:
    """Look for this company's missing fields. Returns the names of the fields that were found."""
    cfg = crawl.settings()
    steps = set(steps or methods.ENRICH_STEP_KEYS)
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return []
        fields = contacts.fields_for(s, rec)
        gids = contacts.member_ids(s, rec.id) + contacts.open_item_group_ids(s, rec.id)
        group = s.get(Group, gids[0]) if gids else None
        group_name = group.name if group else "contacts"
        guidance = " ".join(dict.fromkeys(g.enrich_instructions for g in (s.get(Group, x) for x in gids)
                                          if g and g.enrich_instructions))
        keywords = [k.text for x in gids for k in (s.get(Group, x).keywords if s.get(Group, x) else [])][:6]
        data, social = dict(rec.data or {}), dict(rec.social or {})
        links, ext = dict(rec.links or {}), dict(rec.ext or {})
        name, summary, notes = rec.title, rec.summary, rec.notes or ""
        conn = methods.connections(s)
    by_key = {f.key: f for f in fields}
    wanted = [f for f in fields if f.source != "manual"]
    missing = [f for f in wanted if refresh or empty(data.get(f.key))]
    social_before = {k for k in crawl.SOCIAL if social.get(k)}
    city, country = str(data.get("city") or ""), str(data.get("country") or "")
    place = ", ".join(x for x in (city, country) if x)
    tokens = name_tokens(name)
    found: dict = {}
    found_src: dict = {}
    description = None
    read_sites: set = set()
    if notes:
        guidance = (guidance + " Notes from the team: " + notes).strip()

    def still_missing(ai_only=True):
        return [f for f in missing if f.key not in found and (searchable(f) or not ai_only)]

    def known():
        return {k: v for k, v in {**data, **found}.items() if not empty(v)}

    def merge(result, source):
        nonlocal description
        if not result or result.get("same_company") is False:
            return
        values = result.get("fields") if isinstance(result.get("fields"), dict) else {}
        for f in still_missing():
            v = clean(f, values.get(f.key))
            if not empty(v):
                found[f.key], found_src[f.key] = v, source
        if not description and result.get("description") and (not summary or refresh):
            description = str(result["description"])[:1000]

    def merge_code(page, own_site: bool):
        info = extract.analyze(page.html, page.text, page.final_url or page.url)
        ctx.trace("code", page.final_url or page.url, found=info, own_site=own_site)
        website = found.get("website") or data.get("website")
        base = {**data, **found}
        if refresh:
            base = {k: v for k, v in base.items() if k in found}
        for k, v in extract.fill_fields(still_missing(), info, base, website).items():
            if k in found:
                continue
            if not own_site:   # from other sites, trust only emails on the company's own domain
                f = by_key.get(k)
                own = url_domain(website) if website else None
                if not (f and f.type == "email" and own and v.split("@")[-1].endswith(own)):
                    continue
            found[k], found_src[k] = v, page.final_url or page.url
        if own_site:
            for kind, url in info["social"].items():
                social.setdefault(kind, url)

    def read_own_site(website: str):
        home_url = homepage(website)
        if home_url in read_sites:
            return
        read_sites.add(home_url)
        ctx.step("crawling", f"Enrich {name}: reading {home_url}")
        home = crawl.get_page(home_url)
        if not ctx.count_page(home):
            return
        pages = [home]
        for u in crawl.site_pages(home, int(cfg.get("site_pages") or 8)):
            if ctx.should_stop() or not still_missing():
                break
            ctx.step("crawling", f"Enrich {name}: reading {u}")
            p = crawl.get_page(u)
            if ctx.count_page(p):
                pages.append(p)
        for p in pages:   # code first
            merge_code(p, own_site=True)
        if still_missing():   # then the AI, on the most useful pages, for whatever code couldn't find
            info = {"name": name, "place": place, "known": known()}
            for p in pages[:4]:
                if not still_missing() or ctx.should_stop():
                    break
                ctx.step("extracting", f"Enrich {name}: {p.final_url or p.url}")
                for part in crawl.chunks(p.text, limit=2):
                    merge(_ask_enrich(ctx, group_name, guidance, info, still_missing(), p.final_url or p.url, part),
                          p.final_url or p.url)
                    if not still_missing():
                        break
                ctx.wait()

    # 0. marketplace: the eBay seller, when we know it
    seller = ext.get("ebay") or contacts.marketplace_id("ebay", links.get("ebay", ""))
    if "ebay" in steps and seller and ebay.ready(conn):
        ctx.step("searching", f"Enrich {name}: eBay seller {seller}")
        try:
            products = data.get("products") if isinstance(data.get("products"), list) else []
            info = ebay.lookup_seller(conn, seller, list(products)[:2] + keywords + [name])
        except ebay.EbayError as e:
            info = None
            ctx.notes.append(str(e))
        if info:
            ctx.trace("code", info.get("store_url", ""), found=info)
            for k, v in ebay.values_for(still_missing(ai_only=False), info).items():
                found[k], found_src[k] = v, info["store_url"]
            ext["ebay"], links["ebay"] = seller.lower(), links.get("ebay") or info["store_url"]

    # 1. the company's own website first, when we know it
    if "website" in steps and data.get("website"):
        read_own_site(data["website"])

    # 2. search for what is still missing
    queries = []
    if steps & {"find_site", "web"}:
        queries.append(f'"{name}" {place}'.strip())
    if "web" in steps:
        for f in still_missing()[:4]:
            words = " ".join(f.word_list()[:2]) or f.name
            queries.append(f'"{name}" {city} {words}'.strip())
    if "social" in steps:
        for kind in [k for k in crawl.SOCIAL if not social.get(k)]:
            queries.append(f'"{name}" {city} site:{crawl.SOCIAL[kind]}'.strip())

    other_pages: list[str] = []
    snippets = []
    for q in queries:
        if ctx.should_stop() or (not still_missing() and not [k for k in crawl.SOCIAL if not social.get(k)]):
            break
        ctx.step("searching", f"Enrich {name}: {q}")
        results = crawl.search(q)[:8]
        ctx.trace("search", q, results=[r["url"] for r in results])
        for res in results:
            ctx.stats["results"] += 1
            head = f"{res['title']} {res['content']}"
            kind = crawl.social_kind(res["url"])
            if kind and not social.get(kind) and mentions(res["title"], tokens) and "social" in steps:
                social[kind] = res["url"]
            if mentions(head, tokens):
                snippets.append(f"- {res['title']}: {res['content']} ({res['url']})")
                if not crawl.skip(res["url"]) and res["url"] not in other_pages:
                    other_pages.append(res["url"])

    # 3. a website found along the way? read it properly
    website = found.get("website") or data.get("website")
    if not website and "find_site" in steps:
        for u in other_pages[:3]:
            d = url_domain(u) or ""
            if any(t in d for t in tokens):
                website = homepage(u)
                if "website" in by_key and "website" in [f.key for f in still_missing()]:
                    found["website"], found_src["website"] = website, "search results"
                break
    if website and still_missing() and "website" in steps:
        read_own_site(website)

    # 4. other pages that mention the company
    read = 0
    for url in (other_pages if "web" in steps else []):
        if read >= ENRICH_PAGES or not still_missing() or ctx.should_stop():
            break
        if website and url_domain(url) == url_domain(website):
            continue
        ctx.step("crawling", f"Enrich {name}: reading {url}")
        p = crawl.get_page(url)
        if not ctx.count_page(p):
            continue
        read += 1
        if not mentions(p.text, tokens):
            continue
        merge_code(p, own_site=False)
        ctx.step("extracting", f"Enrich {name}: {url}")
        info = {"name": name, "place": place, "known": known()}
        merge(_ask_enrich(ctx, group_name, guidance, info, still_missing(), url, crawl.chunks(p.text, limit=1)[0]),
              url)
        ctx.wait()

    # 5. search-result snippets (also covers social pages, which can't be opened)
    if "web" in steps and still_missing() and snippets and not ctx.should_stop():
        ctx.step("extracting", f"Enrich {name}: search results")
        info = {"name": name, "place": place, "known": known()}
        merge(_ask_enrich(ctx, group_name, guidance, info, still_missing(), "search engine results",
                          "\n".join(snippets)[:8000]), "search results")

    # 6. save
    new_social = [k for k in crawl.SOCIAL if social.get(k) and k not in social_before]
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return []
        d, src = dict(rec.data or {}), dict(rec.sources or {})
        for k, v in found.items():
            if refresh or empty(d.get(k)):
                d[k], src[k] = v, found_src[k]
        rec.data, rec.sources, rec.social = d, src, social
        rec.links, rec.ext = {**(rec.links or {}), **links}, {**(rec.ext or {}), **ext}
        rec.domain = rec.domain or url_domain(d.get("website"))
        if description:
            rec.summary = description
        rec.enrich_runs = (rec.enrich_runs or 0) + 1
        rec.last_enriched_at = datetime.utcnow()
        rec.enrich_tonight = False
        names = [by_key[k].name for k in found if k in by_key] + [k.capitalize() for k in new_social]
        rec.enrich_note = ("Found: " + ", ".join(names)) if names else "No new information found"
        s.commit()
    ctx.stats["fields"] += len(found) + len(new_social)
    if found or new_social:
        ctx.stats["updated"] += 1
    return names


# ---------- night batch ----------

def night_settings(s) -> dict:
    return {**NIGHT_DEFAULTS, **(get_setting(s, "night", {}) or {})}


def _t(hhmm: str):
    h, m = (hhmm or "0:0").split(":")
    return int(h) * 60 + int(m)


def in_window(cfg: dict, now: datetime) -> bool:
    start, stop, t = _t(cfg["start"]), _t(cfg["stop"]), now.hour * 60 + now.minute
    return start <= t < stop if start < stop else (t >= start or t < stop)


def night_date(cfg: dict, now: datetime) -> date:
    """The date a night started on (a 23:00–07:00 window at 02:00 belongs to yesterday)."""
    start, stop, t = _t(cfg["start"]), _t(cfg["stop"]), now.hour * 60 + now.minute
    if start > stop and t < stop:
        return (now - timedelta(days=1)).date()
    return now.date()


def local_now(cfg: dict) -> datetime:
    try:
        return datetime.now(ZoneInfo(cfg.get("timezone") or "Asia/Karachi")).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def run_night(ctx: Ctx, run_id: int):
    resumed = dict(ctx.resume_state or {})
    with SessionLocal() as s:
        cfg = night_settings(s)
        run = s.get(NightRun, run_id)
        started = run.started_at if run else datetime.utcnow()
        groups = s.scalars(select(Group).order_by(Group.position, Group.id)).all()
        plan = []
        for g in groups:
            if not g.night_discover:
                continue
            for k in g.keywords:
                if not k.night or (k.last_run_at and k.last_run_at >= started):   # done earlier tonight
                    continue
                if control.rejected_entry(s, k.text, g.id):
                    continue
                plan.append((g.id, k.id, k.text, methods.keyword_methods(g, k)))
        enrich_groups = {g.id: g for g in groups if g.night_enrich}
        refresh_groups = {g.id: g.refresh_days for g in groups if g.refresh_days}
        for g in groups:
            _ = g.fields
    ctx.stop_rule = lambda: not in_window(cfg, local_now(cfg))
    ctx.pause = float(cfg.get("pause") or 0)
    ctx.stats.update({"companies": ctx.stats.get("companies", 0)})

    # 1. Discover with each night keyword (results go to the Inbox)
    for gid, kid, text, use in plan:
        if ctx.should_stop():
            break
        before = ctx.stats["saved"]
        ctx.resume_state = {}
        discover(ctx, gid, text, use)
        _keyword_done(kid, ctx.stats["saved"] - before)

    # 2. Enrich: incomplete contacts (least complete first), flagged "enrich tonight", new Inbox items; 3. refresh
    limit = int(cfg.get("max_companies") or 0)
    with SessionLocal() as s:
        now = datetime.utcnow()
        todo, refresh, seen = [], [], set()
        flagged = s.scalars(select(Record.id).where(Record.enrich_tonight)).all()
        rows = s.execute(select(Membership.group_id, Record).join(Record, Record.id == Membership.record_id)
                         .where(Membership.group_id.in_(list(enrich_groups) + list(refresh_groups) or [-1]))).all()
        for gid, r in rows:
            if r.id in seen:
                continue
            g = enrich_groups.get(gid)
            recent = r.last_enriched_at and now - r.last_enriched_at < timedelta(days=3)
            if g and not recent:
                filled, total = completeness(r, g)
                if filled < total:
                    todo.append((filled, r.id))
                    seen.add(r.id)
                    continue
            days = refresh_groups.get(gid)
            if days and (not r.last_enriched_at or now - r.last_enriched_at > timedelta(days=days)):
                refresh.append(r.id)
                seen.add(r.id)
        inbox_ids = []
        if cfg.get("enrich_inbox", True):
            inbox_ids = s.scalars(select(InboxItem.record_id).join(Record, Record.id == InboxItem.record_id)
                                  .where(InboxItem.status == "new", InboxItem.group_id.in_(list(enrich_groups) or [-1]),
                                         Record.enrich_runs == 0).order_by(InboxItem.created_at)).all()
    todo.sort()
    queue = [(rid, False) for rid in flagged] + [(rid, False) for _, rid in todo] \
        + [(rid, False) for rid in inbox_ids if rid not in seen] + [(rid, True) for rid in refresh]
    done_ids = set(resumed.get("enriched") or [])
    for rid, is_refresh in list(dict.fromkeys(queue))[:limit or None]:
        if ctx.should_stop():
            break
        if rid in done_ids:
            continue
        enrich(ctx, rid, refresh=is_refresh)
        done_ids.add(rid)
        ctx.state = {"enriched": sorted(done_ids)}
        ctx.stats["companies"] += 1
        _night_progress(run_id, ctx.stats)

    stopped = ctx.stop_rule()
    with SessionLocal() as s:
        run = s.get(NightRun, run_id)
        if run:
            run.status = "stopped" if stopped else "done"
            run.ended_at = datetime.utcnow()
            run.stats = dict(ctx.stats)
            run.note = "Stopped at the end of the night window." if stopped else "Finished all work."
            s.commit()


def _night_progress(run_id, stats):
    with SessionLocal() as s:
        run = s.get(NightRun, run_id)
        if run:
            run.stats = dict(stats)
            s.commit()


def _keyword_done(keyword_id: int | None, found: int):
    if not keyword_id:
        return
    with SessionLocal() as s:
        kw = s.get(Keyword, keyword_id)
        if kw:
            kw.last_run_at = datetime.utcnow()
            kw.found_count = (kw.found_count or 0) + max(found, 0)
            s.commit()


# ---------- entry point for the queue ----------

def summary(stats: dict) -> str:
    extra = []
    if stats.get("next_pages"):
        extra.append(f"{stats['next_pages']} next pages")
    if stats.get("profiles"):
        extra.append(f"{stats['profiles']} profiles")
    if stats.get("rendered"):
        extra.append(f"{stats['rendered']} via browser")
    if stats.get("cached"):
        extra.append(f"{stats['cached']} from cache")
    return (f"{stats.get('results', 0)} results · {stats.get('read', 0)} pages read"
            + (f" ({', '.join(extra)})" if extra else "")
            + f" · {stats.get('failed', 0)} failed · {stats.get('saved', 0)} new in Inbox, "
              f"{stats.get('updated', 0)} updated")


def _finish(job_id: int, status: str, message: str, stats: dict, state: dict | None = None):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status, job.message, job.stats = status, message[:500], dict(stats)
        job.saved, job.updated = stats.get("saved", 0), stats.get("updated", 0)
        job.control = ""
        job.state = state or {}
        if status != "paused":
            job.finished_at = datetime.utcnow()
        s.commit()


def run_job(job_id: int, keyword_id: int | None = None, run_id: int | None = None):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if not job or job.deleted_at or job.status != "queued":
            return   # stopped, paused, deleted or already running
        if job.control == "pause":
            job.status, job.control = "paused", ""
            s.commit()
            return
        if job.control == "stop":
            job.status, job.control = "stopped", ""
            s.commit()
            return
        job.status, job.started_at = "running", job.started_at or datetime.utcnow()
        params = dict(job.params or {})
        kind, query, group_id, record_id, state = job.kind, job.query, job.group_id, job.record_id, dict(job.state or {})
        user = s.get(User, job.user_id) if job.user_id else None
        uname = user.username if user else ""
        rejected = kind in control.DISCOVER_KINDS and control.rejected_entry(s, query, group_id)
        s.commit()
    keyword_id = keyword_id or params.get("keyword_id")
    run_id = run_id or params.get("run_id")
    ctx = Ctx(job_id, "night" if kind == "night" else ("enrich" if kind == "enrich" else "discover"), user=uname)
    ctx.resume_state = state
    ctx.stats.update({k: v for k, v in (state.get("stats") or {}).items() if k in ctx.stats or k == "companies"})
    try:
        if rejected:
            _finish(job_id, "rejected", "This keyword is on the reject list, so it was not searched.", ctx.stats)
            return
        if kind == "enrich":
            names = enrich(ctx, record_id, steps=params.get("steps"))
            msg = ("Found: " + ", ".join(names)) if names else "No new information found"
            message = f"{msg} · {ctx.stats['read']} pages read"
        elif kind == "night":
            run_night(ctx, run_id)
            message = f"Night run: {ctx.stats.get('companies', 0)} companies enriched · " + summary(ctx.stats)
        else:
            if not group_id:
                _finish(job_id, "failed", "This request has no directory. Choose one and try again.", ctx.stats)
                return
            use = params.get("methods")
            if not use and keyword_id:
                with SessionLocal() as s:
                    kw, g = s.get(Keyword, keyword_id), s.get(Group, group_id)
                    use = methods.keyword_methods(g, kw) if kw and g else None
            discover(ctx, group_id, query, use)
            _keyword_done(keyword_id, ctx.stats["saved"])
            message = summary(ctx.stats)
        if ctx.notes:
            message += " · " + " ".join(dict.fromkeys(ctx.notes))
        _finish(job_id, "done", message, ctx.stats)
    except Paused:
        _score_new(ctx)
        _finish(job_id, "paused", "Paused · " + summary(ctx.stats), ctx.stats, {**ctx.state, "stats": ctx.stats})
        if run_id:
            with SessionLocal() as s:
                run = s.get(NightRun, run_id)
                if run:
                    run.status, run.stats = "paused", dict(ctx.stats)
                    s.commit()
    except Stopped:
        _score_new(ctx)
        final = "rejected" if params.get("reject") else "stopped"
        _finish(job_id, final, ("Rejected" if final == "rejected" else "Stopped") + " · " + summary(ctx.stats),
                ctx.stats)
        if run_id:
            with SessionLocal() as s:
                run = s.get(NightRun, run_id)
                if run:
                    run.status, run.ended_at, run.note = "stopped", datetime.utcnow(), "Stopped by a user."
                    s.commit()
    except Exception as e:  # show the error in the UI instead of failing silently
        _finish(job_id, "failed", f"{type(e).__name__}: {e}", ctx.stats)
        log("error", "worker", f"Request {job_id} failed: {type(e).__name__}: {e}")
        if run_id:
            with SessionLocal() as s:
                run = s.get(NightRun, run_id)
                if run:
                    run.status, run.ended_at, run.note = "failed", datetime.utcnow(), f"{type(e).__name__}: {e}"
                    s.commit()
        raise
