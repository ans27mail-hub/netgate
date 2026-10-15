"""Background job: search -> crawl -> ask the local LLM to extract -> add or update listings in a group."""
import json
import os

import httpx
import trafilatura
from sqlalchemy import select

from .db import Group, Job, Record, SessionLocal

SEARXNG_URL = os.environ["SEARXNG_URL"]
OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL = os.environ.get("MODEL", "qwen3:8b")
MAX_PAGES = int(os.environ.get("MAX_PAGES", 5))

TYPE_HINTS = {
    "text": "short text, or null if not found",
    "list": "list of short strings (empty list if not found)",
    "number": "a number, or null if not found",
    "email": "an email address, or null if not found",
    "url": "a website address, or null if not found",
}

PROMPT = """You collect information for the "{group}" section of a business directory.
About this section: {instructions}
The user is looking for: {query}

Page address: {url}
Page text:
{text}

Return JSON only, with these keys:
"relevant": true only if this page is about ONE specific {group} entry that matches what the user is looking for (a company, product, event...). A list or directory of many entries, a news article or an unrelated page is false.
"title": the name of that entry (e.g. the company name)
"summary": 2-3 sentences about it, relevant to what the user is looking for
"facts": list of short factual bullet strings (products, certifications, dates, prices, contact details)
"fields": an object with exactly these keys:
{fields}"""


def _field_line(f) -> str:
    if f.type == "choice":
        options = ", ".join(f'"{c}"' for c in f.choice_list())
        hint = f'exactly one of {options}, or "Unknown" if not stated'
    else:
        hint = TYPE_HINTS.get(f.type, TYPE_HINTS["text"])
    return f'  "{f.key}": {f.name} - {hint}'


def _clean(f, value):
    """Make the model's value fit the field type."""
    if f.type == "list":
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",")]
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()][:15]
    if isinstance(value, list):
        value = value[0] if value else None
    if value in (None, "", "null", "None"):
        return "Unknown" if f.type == "choice" else None
    if f.type == "choice":
        value = str(value).strip()
        choices = f.choice_list()
        return value if value in choices else "Unknown"
    if f.type == "number":
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None
    return str(value).strip()[:300]


def _update_job(job_id: int, **values):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        for k, v in values.items():
            setattr(job, k, v)
        s.commit()


def search(query: str) -> list[str]:
    r = httpx.get(f"{SEARXNG_URL}/search", params={"q": query, "format": "json"}, timeout=30)
    r.raise_for_status()
    urls, seen = [], set()
    for res in r.json().get("results", []):
        url = res.get("url")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls[:MAX_PAGES]


def fetch_text(url: str) -> str | None:
    try:
        html = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "NetGate/0.2"}).text
    except httpx.HTTPError:
        return None
    text = trafilatura.extract(html)
    return text[:8000] if text else None  # keep within an 8B model's comfortable context


def extract(query: str, group, url: str, text: str) -> dict | None:
    prompt = PROMPT.format(
        group=group.name, instructions=group.instructions or "-", query=query, url=url, text=text,
        fields="\n".join(_field_line(f) for f in group.fields) or "  (none)",
    )
    r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=300, json={
        "model": MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "think": False,  # qwen3/deepseek-r1: skip long reasoning, answer directly
        "options": {"temperature": 0.1},
    })
    r.raise_for_status()
    try:
        return json.loads(r.json()["response"])
    except (json.JSONDecodeError, KeyError):
        return None


def run_job(job_id: int):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        group = s.get(Group, job.group_id) if job.group_id else None
        query, kind = job.query, job.kind
        if group:
            _ = group.fields  # load before the session closes
    if not group:
        _update_job(job_id, status="failed", message="This request has no group. Choose a group and try again.")
        return
    try:
        search_query = f"{query} {group.search_terms}".strip() if kind == "keyword" else query
        _update_job(job_id, status="searching", message=f"Searching: {search_query}")
        urls = search(search_query)
        saved = updated = 0
        for i, url in enumerate(urls, 1):
            _update_job(job_id, status="crawling", message=f"Page {i} of {len(urls)}: {url}")
            text = fetch_text(url)
            if not text:
                continue
            _update_job(job_id, status="extracting", message=f"Page {i} of {len(urls)}: {url}")
            data = extract(query, group, url, text)
            if not data or not data.get("relevant"):
                continue
            raw_fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
            field_values = {f.key: _clean(f, raw_fields.get(f.key)) for f in group.fields}
            facts = data.get("facts") or []
            facts = "\n".join(map(str, facts)) if isinstance(facts, list) else str(facts)
            with SessionLocal() as s:
                rec = s.scalar(select(Record).where(Record.group_id == group.id, Record.source_url == url))
                if rec:
                    # keep values the AI could not find this time
                    merged = dict(rec.data or {})
                    merged.update({k: v for k, v in field_values.items() if v not in (None, [], "Unknown")})
                    rec.title = str(data.get("title") or rec.title)[:500]
                    rec.summary = str(data.get("summary") or rec.summary)
                    rec.facts = facts or rec.facts
                    rec.data = merged
                    rec.topic = query
                    rec.job_id = job_id
                    updated += 1
                else:
                    s.add(Record(job_id=job_id, group_id=group.id, topic=query, source_url=url,
                                 title=str(data.get("title") or url)[:500], summary=str(data.get("summary") or ""),
                                 facts=facts, data=field_values))
                    saved += 1
                s.commit()
            _update_job(job_id, saved=saved, updated=updated)
        _update_job(job_id, status="done", saved=saved, updated=updated,
                    message=f"{saved} saved, {updated} updated from {len(urls)} page(s).")
    except Exception as e:  # show the error in the UI instead of failing silently
        _update_job(job_id, status="failed", message=f"{type(e).__name__}: {e}")
        raise
