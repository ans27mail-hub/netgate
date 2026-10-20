---
title: List of pages read (skip and reuse)
order: 48
updated: v0.9
---
**What it does:** every page NetGate reads is written to `pages_read` with what was found on it. Discovery skips list pages read recently for the same directory and pages of earlier tries; Enrich doesn't open a company's pages again and reuses what code found there. Shown on the Debug page and the big card. Kept permanently — the base of Saved Pages later.

## How it works
- `app/pages.py`: `record(page, job_id, purpose, group_id, record_id)` (purpose: `list`, `profile`, `site`, `other`), `add_found(row_id, companies=[…], code={…}, filled=[…])`, `read_before_for_list()`, `read_for_record()`, `for_job()`, `for_record()`, `summary()`.
- URLs are normalised (`pages.norm`: no `#part`, no trailing slash on paths).
- `Ctx.read()` records only in real requests (`job_id` set) — the Page Tester saves nothing.
- Discovery: `crawler.reread_days` (Settings → Crawler), default 7, 0 = read again; earlier tries of the same request are always skipped.
- Enrich: see the Enrich page (`open_page`, `merge_info`, `refresh`).

## Data
`pages_read` (url, final_url, at, job_id, group_id, record_id, purpose, ok, chars, rendered, found JSON, note). No foreign keys: rows outlive requests and contacts.

## Tests
`test_v09.py` (recording, skip per directory, other directory, 0 days, earlier tries, Enrich reuse, Check All Again, Debug, big card).

## Limits & ideas
Only what code found is reused (the page text itself is in the page cache for a few days). Saved Pages will keep page versions.
