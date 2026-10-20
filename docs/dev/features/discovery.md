---
title: Discovery (finding companies)
order: 30
updated: v0.9
---
**What it does:** turns a keyword into new companies in the Inbox.

## How it works
1. Started by **Run Discovery**, a keyword chip / **Run All Keywords**, or the night run → `start_job()` → a `jobs` row + RQ job → `jobs.run_job()`.
2. `discover()` runs each chosen method (people without *See search methods* always use all of the directory's methods):
   - **web** — `discover_queries()`: the keyword (+ directory search words), `… list`, `top … companies`, page 2 → up to `MAX_PAGES` (15) result pages. **Go deeper** (v0.8, `jobs.params.deeper` 1–3, `Ctx.deeper`): per level two more result pages and one more “list” page; `page_limit()` = `MAX_PAGES × (1 + level)`; `crawl_pages` follows 2 more next pages per level; directory method reads more `site:` results; eBay looks at more listings / sellers.
   - **directory** — list pages from settings (`{q}` = keyword) and `site:` searches; profiles and next pages always on.
   - **ebay** — `ebay.find_sellers()` (see eBay).
3. `crawl_pages()` per page: download (cache, robots, delay, renderer when needed) → `_ask_entries()` (AI lists companies, `DISCOVER_PROMPT`, long pages in parts) → `_enhance_entries()` (code finds emails / phones / links on the page or opens up to 15 profile pages) → next page put first in the queue (up to 4) → `save_entry()`.
4. `save_found()` → `contacts.upsert()` (match: eBay id → website domain → name + city; new contact's `found_by` = who started the request) → existing contact found again by someone else → `note_existing_hit()` → `to_inbox()` (not if already in / decided for that directory) → suggestions scored.
5. Pause / Stop are checked every 2 s (`Ctx.check`); state is saved for Resume. Every step goes to the debug trace.

## v0.9 — pages read
`Ctx.read(url, purpose)` downloads, counts and records every page (`pages_read`); `crawl_pages` first asks `pages.read_before_for_list(url, group, job, days)`: a list page read by an earlier try of this request, or for this directory within `crawler.reread_days` (default 7, 0 = off), is skipped (`stats.skipped`, trace note). Companies found on a list page and code finds on profiles are added to its row.

## Files
`app/jobs.py`, `app/crawl.py`, `app/extract.py`, `app/contacts.py`, `app/ai.py`.

Each search is traced with `trace_search()`: links, the engine(s) behind each link and the engines that failed (see Search engines).

## Tests
`test_v05.py` (whole flow), `test_v07.py` (first finder, existing hits), `test_v08.py` (Go deeper, engines in traces).

## Limits & ideas
Small AI model; sites change. Ideas: site recipes (Scanner), Etsy / Amazon methods.
