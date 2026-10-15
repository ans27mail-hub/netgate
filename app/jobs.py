"""Background jobs: Discover (find companies), Enrich (fill missing fields) and the night batch."""
import json
import math
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import ai, crawl
from .db import (DISCOVER_KEYS, Group, Job, Keyword, NightRun, Record, SessionLocal, get_setting, name_key,
                 url_domain)

MAX_PAGES = int(os.environ.get("MAX_PAGES", 15))        # pages read per Discover
ENRICH_PAGES = int(os.environ.get("ENRICH_PAGES", 6))   # pages read per Enrich

NIGHT_DEFAULTS = {"enabled": False, "start": "23:00", "stop": "07:00", "days": [0, 1, 2, 3, 4, 5],
                  "max_companies": 150, "pause": 3, "timezone": "Asia/Karachi"}

TYPE_HINTS = {
    "text": "short text, or null",
    "list": "list of short strings, or []",
    "number": "a number, or null",
    "email": "an email address, or null",
    "url": "a website address, or null",
    "phone": "a phone number with country code if shown, or null",
}


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


class Ctx:
    """Progress, counters and stop rules for one job."""

    def __init__(self, job_id: int, ai_type: str, stop_rule=None, pause: float = 0.0):
        self.job_id, self.ai_type, self.stop_rule, self.pause = job_id, ai_type, stop_rule, pause
        self.stats = {"results": 0, "read": 0, "failed": 0, "saved": 0, "updated": 0, "fields": 0}

    def step(self, status: str, message: str):
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job:
                job.status, job.message, job.stats = status, message[:500], dict(self.stats)
                job.saved, job.updated = self.stats["saved"], self.stats["updated"]
                s.commit()

    def should_stop(self) -> bool:
        return bool(self.stop_rule and self.stop_rule())

    def wait(self):
        if self.pause:
            time.sleep(self.pause)


# ---------- Discover ----------

DISCOVER_PROMPT = """You collect companies for the "{group}" section of a business directory.
What belongs in this section: {instructions}
Skip: {ignore}
The user is looking for: {query}

Page address: {url}
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


def find_match(s, group_id: int, nk: str, dom: str | None, city: str | None):
    if dom:
        rec = s.scalar(select(Record).where(Record.group_id == group_id, Record.domain == dom).limit(1))
        if rec:
            return rec
    if nk:
        candidates = s.scalars(select(Record).where(Record.group_id == group_id, Record.name_key == nk)).all()
        city_l = (city or "").strip().lower()
        for rec in candidates:
            rec_city = str((rec.data or {}).get("city") or "").strip().lower()
            if not city_l or not rec_city or rec_city == city_l:
                return rec
    return None


def save_entry(s, ctx: Ctx, group, entry: dict, page_url: str, query: str) -> str | None:
    """Add a new company or fill gaps in an existing one. Returns 'saved', 'updated' or None."""
    name = str(entry.get("name") or "").strip()
    if len(name) < 2 or len(name) > 150:
        return None
    by_key = {f.key: f for f in group.fields}
    raw = dict(entry.get("fields") or {}) if isinstance(entry.get("fields"), dict) else {}
    for k in DISCOVER_KEYS:
        if entry.get(k) not in (None, ""):
            raw.setdefault(k, entry.get(k))
    values = {}
    for key, value in raw.items():
        f = by_key.get(key)
        if f:
            v = clean(f, value)
            if not empty(v):
                values[key] = v
    nk = name_key(name)
    dom = url_domain(values.get("website"))
    rec = find_match(s, group.id, nk, dom, values.get("city"))
    if rec is None:
        rec = Record(job_id=ctx.job_id, group_id=group.id, topic=query, title=name[:300],
                     summary=str(entry.get("description") or "")[:1000], facts="", data=values,
                     sources={k: page_url for k in values}, social={}, source_url=page_url, name_key=nk, domain=dom)
        s.add(rec)
        return "saved"
    data, sources = dict(rec.data or {}), dict(rec.sources or {})
    changed = False
    for k, v in values.items():
        if empty(data.get(k)):
            data[k], sources[k], changed = v, page_url, True
    if not rec.summary and entry.get("description"):
        rec.summary, changed = str(entry["description"])[:1000], True
    if changed:
        rec.data, rec.sources = data, sources
        rec.domain = rec.domain or url_domain(data.get("website"))
        return "updated"
    return None


def discover(ctx: Ctx, group_id: int, query: str):
    with SessionLocal() as s:
        group = s.get(Group, group_id)
        _ = group.fields
    seen, urls = set(), []
    for q, pageno in discover_queries(query, group):
        if len(urls) >= MAX_PAGES or ctx.should_stop():
            break
        ctx.step("searching", f"Searching: {q}" + (" (page 2)" if pageno > 1 else ""))
        for res in crawl.search(q, pageno):
            ctx.stats["results"] += 1
            u = res["url"]
            if u not in seen and not crawl.skip(u):
                seen.add(u)
                urls.append(u)
    urls = urls[:MAX_PAGES]
    discover_fields = [f for f in group.fields if f.stage == "discover" and f.key not in DISCOVER_KEYS]
    for i, url in enumerate(urls, 1):
        if ctx.should_stop():
            break
        ctx.step("crawling", f"Page {i} of {len(urls)}: {url}")
        _, text = crawl.fetch(url)
        if not text:
            ctx.stats["failed"] += 1
            continue
        ctx.stats["read"] += 1
        ctx.step("extracting", f"Page {i} of {len(urls)}: {url}")
        prompt = DISCOVER_PROMPT.format(
            group=group.name, instructions=group.instructions or "-", ignore=group.ignore_instructions or "-",
            query=query, url=url, text=text, fields="\n".join(field_line(f) for f in discover_fields) or "    (none)")
        try:
            data = ai.ask_json(ctx.ai_type, prompt)
        except Exception as e:  # one bad page should not stop the whole job
            ctx.stats["failed"] += 1
            ctx.step("extracting", f"AI error on page {i}: {type(e).__name__}")
            continue
        entries = (data or {}).get("entries") or []
        with SessionLocal() as s:
            group = s.get(Group, group_id)
            for entry in entries[:40] if isinstance(entries, list) else []:
                if isinstance(entry, dict):
                    result = save_entry(s, ctx, group, entry, url, query)
                    if result:
                        ctx.stats[result] += 1
                    s.flush()
            s.commit()
        ctx.wait()
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


def _ask_enrich(ctx, group, rec_info, missing, source, text):
    prompt = ENRICH_PROMPT.format(
        group=group.name, name=rec_info["name"], place=rec_info["place"] or "location unknown",
        known=json.dumps(rec_info["known"], ensure_ascii=False)[:1500],
        guidance=group.enrich_instructions or "Prefer the company's own website.",
        source=source, text=text, fields="\n".join(field_line(f) for f in missing))
    try:
        return ai.ask_json(ctx.ai_type, prompt)
    except Exception:
        ctx.stats["failed"] += 1
        return None


def enrich(ctx: Ctx, record_id: int, refresh: bool = False) -> list[str]:
    """Look for this company's missing fields. Returns the names of the fields that were found."""
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return []
        group = s.get(Group, rec.group_id) if rec.group_id else None
        if not group:
            return []
        _ = group.fields
        data, sources, social = dict(rec.data or {}), dict(rec.sources or {}), dict(rec.social or {})
        name, summary = rec.title, rec.summary
    by_key = {f.key: f for f in group.fields}
    missing = [f for f in group.fields if refresh or empty(data.get(f.key))]
    social_missing = [k for k in crawl.SOCIAL if not social.get(k)]
    city, country = str(data.get("city") or ""), str(data.get("country") or "")
    place = ", ".join(x for x in (city, country) if x)
    tokens = name_tokens(name)
    found: dict = {}
    found_src: dict = {}
    description = None

    def still_missing():
        return [f for f in missing if f.key not in found]

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

    # 1. what to search for
    queries = [f'"{name}" {place}'.strip()]
    for f in missing[:4]:
        words = " ".join(f.word_list()[:2]) or f.name
        queries.append(f'"{name}" {city} {words}'.strip())
    for kind in social_missing:
        queries.append(f'"{name}" {city} site:{crawl.SOCIAL[kind]}'.strip())

    pages: list[str] = []
    website = data.get("website") or found.get("website")
    if website:
        pages.append(website)
    snippets = []
    for q in queries:
        if ctx.should_stop():
            break
        ctx.step("searching", f"Enrich {name}: {q}")
        for res in crawl.search(q)[:8]:
            ctx.stats["results"] += 1
            head = f"{res['title']} {res['content']}"
            kind = crawl.social_kind(res["url"])
            if kind and kind in social_missing and kind not in social and mentions(res["title"], tokens):
                social[kind] = res["url"]
            if mentions(head, tokens):
                snippets.append(f"- {res['title']}: {res['content']} ({res['url']})")
                if not crawl.skip(res["url"]) and res["url"] not in pages:
                    pages.append(res["url"])
        ctx.wait()

    # 2. read pages (the company's own site first)
    read = 0
    i = 0
    while i < len(pages) and read < ENRICH_PAGES and still_missing() and not ctx.should_stop():
        url = pages[i]
        i += 1
        ctx.step("crawling", f"Enrich {name}: reading {url}")
        html, text = crawl.fetch(url)
        if not text:
            ctx.stats["failed"] += 1
            continue
        ctx.stats["read"] += 1
        read += 1
        own_site = website and url_domain(url) == url_domain(website)
        if own_site and html:
            for link in crawl.inner_links(url, html):
                if link not in pages:
                    pages.insert(i, link)
        if not own_site and not mentions(text, tokens):
            continue
        ctx.step("extracting", f"Enrich {name}: {url}")
        info = {"name": name, "place": place, "known": {k: v for k, v in data.items() if not empty(v)}}
        merge(_ask_enrich(ctx, group, info, still_missing(), url, text), url)
        ctx.wait()

    # 3. search-result snippets (also covers social pages, which can't be opened)
    if still_missing() and snippets and not ctx.should_stop():
        ctx.step("extracting", f"Enrich {name}: search results")
        info = {"name": name, "place": place, "known": {k: v for k, v in data.items() if not empty(v)}}
        merge(_ask_enrich(ctx, group, info, still_missing(), "search engine results", "\n".join(snippets)[:8000]),
              "search results")

    # 4. save
    new_social = [k for k in crawl.SOCIAL if social.get(k) and k in social_missing]
    with SessionLocal() as s:
        rec = s.get(Record, record_id)
        if not rec:
            return []
        d, src = dict(rec.data or {}), dict(rec.sources or {})
        for k, v in found.items():
            if refresh or empty(d.get(k)):
                d[k], src[k] = v, found_src[k]
        rec.data, rec.sources, rec.social = d, src, social
        rec.domain = rec.domain or url_domain(d.get("website"))
        if description:
            rec.summary = description
        rec.enrich_runs = (rec.enrich_runs or 0) + 1
        rec.last_enriched_at = datetime.utcnow()
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
    with SessionLocal() as s:
        cfg = night_settings(s)
        groups = s.scalars(select(Group).order_by(Group.position, Group.id)).all()
        plan = [(g.id, [(k.id, k.text) for k in g.keywords if k.night]) for g in groups if g.night_discover]
        enrich_groups = {g.id: g for g in groups if g.night_enrich}
        refresh_groups = {g.id: g.refresh_days for g in groups if g.refresh_days}
        for g in groups:
            _ = g.fields
    ctx.stop_rule = lambda: not in_window(cfg, local_now(cfg))
    ctx.pause = float(cfg.get("pause") or 0)
    ctx.stats.update({"companies": 0})

    # 1. Discover with each night keyword
    for gid, kws in plan:
        for kid, text in kws:
            if ctx.should_stop():
                break
            before = ctx.stats["saved"]
            discover(ctx, gid, text)
            _keyword_done(kid, ctx.stats["saved"] - before)

    # 2. Enrich incomplete companies, least complete first; 3. refresh old ones
    limit = int(cfg.get("max_companies") or 0)
    with SessionLocal() as s:
        recs = s.scalars(select(Record).where(Record.group_id.in_(list(enrich_groups) + list(refresh_groups)
                                                                   or [-1]))).all()
        now = datetime.utcnow()
        todo, refresh = [], []
        for r in recs:
            g = enrich_groups.get(r.group_id)
            recent = r.last_enriched_at and now - r.last_enriched_at < timedelta(days=3)
            if g and not recent:
                filled, total = completeness(r, g)
                if filled < total:
                    todo.append((filled, r.id))
                    continue
            days = refresh_groups.get(r.group_id)
            if days and (not r.last_enriched_at or now - r.last_enriched_at > timedelta(days=days)):
                refresh.append(r.id)
    todo.sort()
    queue = [(rid, False) for _, rid in todo] + [(rid, True) for rid in refresh]
    for rid, is_refresh in queue[:limit or None]:
        if ctx.should_stop():
            break
        enrich(ctx, rid, refresh=is_refresh)
        ctx.stats["companies"] += 1
        _night_progress(run_id, ctx.stats)

    stopped = ctx.should_stop()
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
    return (f"{stats.get('results', 0)} results · {stats.get('read', 0)} pages read · "
            f"{stats.get('failed', 0)} failed · {stats.get('saved', 0)} new, {stats.get('updated', 0)} updated")


def run_job(job_id: int, keyword_id: int | None = None, run_id: int | None = None):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        kind, query, group_id, record_id = job.kind, job.query, job.group_id, job.record_id
    ctx = Ctx(job_id, "night" if kind == "night" else ("enrich" if kind == "enrich" else "discover"))
    try:
        if kind == "enrich":
            names = enrich(ctx, record_id)
            msg = ("Found: " + ", ".join(names)) if names else "No new information found"
            ctx.step("done", f"{msg} · {ctx.stats['read']} pages read")
        elif kind == "night":
            run_night(ctx, run_id)
            ctx.step("done", f"Night run: {ctx.stats.get('companies', 0)} companies enriched · " + summary(ctx.stats))
        else:
            if not group_id:
                ctx.step("failed", "This request has no group. Choose a group and try again.")
                return
            discover(ctx, group_id, query)
            _keyword_done(keyword_id, ctx.stats["saved"])
            ctx.step("done", summary(ctx.stats))
    except Exception as e:  # show the error in the UI instead of failing silently
        ctx.step("failed", f"{type(e).__name__}: {e}")
        if run_id:
            with SessionLocal() as s:
                run = s.get(NightRun, run_id)
                if run:
                    run.status, run.ended_at, run.note = "failed", datetime.utcnow(), f"{type(e).__name__}: {e}"
                    s.commit()
        raise
