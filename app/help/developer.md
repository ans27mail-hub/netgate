---
title: How NetGate is built
section: Developers
order: 10
needs: dev_help
summary: Code, containers, how to run, test and release
---
The full developer guide is in the GitHub repository: **AGENTS.md** (start here), **docs/ARCHITECTURE.md**, **docs/ROADMAP.md** and **docs/DECISIONS.md**. In short:

## Containers (docker-compose.yml)
| Service | What it does |
|---|---|
| web | FastAPI app, the pages you see (port 8090) |
| worker | runs searches and enrich jobs (queue `netgate`) |
| night-worker | runs the night batch (queue `netgate-night`) |
| scheduler | starts the night run, cleans the cache and old requests |
| db | PostgreSQL 16 |
| redis | the job queue |
| renderer | headless Chromium for JavaScript pages |
| searxng | the search engine |

The AI runs outside, on Ollama (the iMac).

## Code
- `app/web/*_routes.py` — pages; `app/templates/` — HTML (Jinja2 + HTMX); `app/static/app.css`.
- `app/jobs.py` — Discover, Enrich, night run; `app/crawl.py` — downloading and reading pages; `app/extract.py` — code-first details; `app/ebay.py` — eBay API.
- `app/contacts.py` — contacts, Inbox, accept / reject; `app/learn.py` — suggestions; `app/control.py` — pause / stop / reject list.
- `app/db.py` — tables and automatic upgrades; `app/auth.py` — permissions and roles.
- `app/help/*.md` — these help pages.

## Rules
- Database changes are upgrades that keep existing data (`MIGRATIONS` and one-time upgrade steps in `db.py`).
- Search methods and site recipes are added in code, never edited in the web page.
- API secrets are never shown back on a page.

## Release
Commit, add a line to `releases.txt` (`v0.x  commit  date  description`), push to GitHub. On the PC, `netgate update` installs it; `netgate rollback` goes back.
