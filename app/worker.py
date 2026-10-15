"""Background job: search -> crawl -> ask local LLM to extract -> add/update records."""
import json
import os

import httpx
import trafilatura
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .db import Job, Record, SessionLocal

SEARXNG_URL = os.environ["SEARXNG_URL"]
OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL = os.environ.get("MODEL", "llama3.1:8b")
MAX_PAGES = int(os.environ.get("MAX_PAGES", 5))

PROMPT = """You extract information for a knowledge base.
Request: {query}

Page text:
{text}

Return JSON only, with keys:
"relevant": true/false (is this page useful for the request),
"title": short title,
"summary": 2-4 sentence summary relevant to the request,
"facts": list of short factual bullet strings (prices, dates, names, specs)."""


def _set_status(job_id: int, status: str, message: str | None = None):
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        job.status = status
        if message is not None:
            job.message = message
        s.commit()


def search(query: str) -> list[str]:
    r = httpx.get(f"{SEARXNG_URL}/search", params={"q": query, "format": "json"}, timeout=30)
    r.raise_for_status()
    return [res["url"] for res in r.json().get("results", [])][:MAX_PAGES]


def fetch_text(url: str) -> str | None:
    try:
        html = httpx.get(url, timeout=20, follow_redirects=True,
                         headers={"User-Agent": "NetGate/0.1"}).text
    except httpx.HTTPError:
        return None
    text = trafilatura.extract(html)
    return text[:8000] if text else None  # keep within an 8B model's comfortable context


def extract(query: str, text: str) -> dict | None:
    r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=300, json={
        "model": MODEL,
        "prompt": PROMPT.format(query=query, text=text),
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
        query = s.get(Job, job_id).query
    try:
        _set_status(job_id, "searching")
        urls = search(query)
        saved = 0
        for i, url in enumerate(urls, 1):
            _set_status(job_id, "crawling", f"Page {i}/{len(urls)}: {url}")
            text = fetch_text(url)
            if not text:
                continue
            _set_status(job_id, "extracting", f"Page {i}/{len(urls)}: {url}")
            data = extract(query, text)
            if not data or not data.get("relevant"):
                continue
            facts = data.get("facts") or []
            values = dict(job_id=job_id, topic=query, title=str(data.get("title", url))[:500],
                          summary=str(data.get("summary", "")),
                          facts="\n".join(map(str, facts)) if isinstance(facts, list) else str(facts),
                          source_url=url)
            stmt = insert(Record).values(**values).on_conflict_do_update(
                index_elements=["source_url"],
                set_={k: v for k, v in values.items() if k != "source_url"} | {"updated_at": func.now()},
            )
            with SessionLocal() as s:
                s.execute(stmt)
                s.commit()
            saved += 1
        _set_status(job_id, "done", f"Saved or updated {saved} record(s) from {len(urls)} page(s).")
    except Exception as e:  # show the error in the UI instead of failing silently
        _set_status(job_id, "failed", f"{type(e).__name__}: {e}")
        raise
