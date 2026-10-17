---
title: Dashboard
order: 10
updated: v0.7
---
**What it does:** the start page (`/`, also `/dashboard`): numbers at a glance, Needs Attention (with a button each), Running Jobs, Quick Actions, System status, a Directories table and Recent Activity.

## How it works
- `dashboard_routes.dashboard()` counts Inbox (new / enriched), contacts and added this week, decisions this week, searches (running / waiting / failed in 24 h) and the last night run.
- **Needs Attention** (`_attention`): backup warning (people with *Backups*), failed requests, eBay keys missing for directories that use eBay, the two directories with the biggest gap for one field (*Enrich Them* → `enrich-incomplete`), keywords never run (*Run Now*), enriched companies ready to decide.
- **Running Jobs** (`/dashboard/jobs`, HTMX every 5 s): running jobs with progress (`stats.page_no / pages_total`), what they do (`jobs.message`), Pause / Stop for people who may control them, and the waiting list.
- **System** (`/dashboard/system`, loaded after the page): checks Ollama (`/api/tags`), renderer (`/health`), SearXNG (`/healthz`) and eBay keys, 3 s each in parallel.
- **Recent Activity** (`_activity`): last decisions + finished searches + night runs.
- Everything respects what the person may see (directories, own contacts, own requests).

## Files
`app/web/dashboard_routes.py`, `templates/dashboard.html`, `_runjobs.html`, `_system.html`.

## Tests
`test_v06.py` (Dashboard), `test_v07.py` (Running Jobs, backup warning).

## Limits & ideas
Counts are computed on every load (fine for thousands of contacts). Ideas: disk-space and queue-stuck warnings.
