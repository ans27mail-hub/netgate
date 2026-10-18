---
title: Crawler and renderer
order: 120
updated: v0.8
---
**What it does:** downloads pages politely and reads them as text.

Web searches go through `crawl.search()` (SearXNG); which engines it asks and how each one is doing is on the *Search engines* page of this Handbook (v0.8).

## How it works
`crawl.get_page()`: page cache (default 3 days) → robots.txt (on) → per-site delay (2 s) → download with retry → if the page looks empty or the site is listed, the **renderer** (`renderer/`, Playwright Chromium, `GET /render?url=`) opens it → trafilatura text. Also: links, next-page detection, sitemap, useful pages (Contact / About / Impressum), skip list (video, social, big marketplaces), long pages split into parts (max 3). Settings → Crawler (`CRAWLER_DEFAULTS`).

## Files
`app/crawl.py`, `app/extract.py`, `renderer/server.py`, `renderer/Dockerfile` (Debian 12 bookworm — Playwright 1.48 can't install on Debian 13).
