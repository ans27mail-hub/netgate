---
title: Code map — where to change what
order: 40
updated: v0.7
---
| File | Responsible for |
|---|---|
| `app/main.py` | Creates the app, includes the page routers, error handlers (login, forbidden, must-change-password, errors → log) |
| `app/db.py` | All tables (SQLAlchemy models), `MIGRATIONS`, one-time upgrades (`_upgrade_v03`, `_upgrade_v05`, `_upgrade_v07`), seeding, `get_setting` / `set_setting`, `log()` |
| `app/auth.py` | Permission list (`PERM_GROUPS`), default roles, `can()`, `own_contacts_only()`, `sees_methods()`, password hashing (scrypt) |
| `app/contacts.py` | Matching (`find_match`), `upsert`, `to_inbox`, accept / reject / restore, add / remove / `move`, `note_existing_hit`, who may see / enrich a contact |
| `app/jobs.py` | `run_job` entry point, `Ctx` (progress, pause / stop checks, debug trace), Discover per method, Enrich steps, night run, AI prompts |
| `app/crawl.py` | Search (SearXNG), polite download (robots, delay, retry, cache), renderer, links, next page, sitemap |
| `app/extract.py` | Code-first extraction: emails (also hidden), phones, WhatsApp, social links, schema.org |
| `app/ai.py` | Calls Ollama / OpenRouter, `ask_json(job_type, prompt)`, model per job, spending limits |
| `app/learn.py` | Vectors, Inbox suggestions (kNN), training-data export |
| `app/methods.py` | Search-method registry, “Filled from” sources, enrich steps, connections (API keys) |
| `app/ebay.py` | eBay Browse API client |
| `app/control.py` | Request actions (pause, resume, stop, delete, reject, run again), reject list, queues, clean-up |
| `app/tags.py` | Tags: list, map per contact, card tint, set / add / remove |
| `app/pages.py` | List of pages read (v0.9): record, skip, reuse, summaries |
| `app/worker.py` | Worker start-up (v0.9): marks leftover requests Interrupted, re-queues waiting ones, then runs `rq worker` |
| `app/engines.py` | Search engines (v0.8): chosen engines, `search_log`, status per engine (working / blocking since …) |
| `app/themes.py` | Built-in themes, colour maths, CSS variables, readability warnings |
| `app/backups.py` | Backup settings / status / files (the `backup` container does the work) |
| `app/help.py` + `app/help/*.md` | Help Center for users |
| `app/handbook.py` + `docs/dev/` | This Handbook (written + automatic pages) |
| `app/scheduler.py` | Night window and hourly clean-up |
| `app/web/common.py` | Templates, `current_user`, `require`, visibility clauses, card settings, theme for a person, `render()` |
| `app/web/dashboard_routes.py` | Dashboard, System status, Running Jobs, Directories page |
| `app/web/contacts_routes.py` | All Contacts, directory page (incl. Existing Contacts tab), big card, edit, move, tags, short-card fields, export, saved views |
| `app/web/inbox_routes.py` | Inbox |
| `app/web/add_routes.py` | Add contact (one / list / CSV) |
| `app/web/requests_routes.py` | Requests page, actions, debug view, starting searches |
| `app/web/settings_routes.py` | Directory settings (incl. Cards, Owner), AI, night, display, crawler, connections, reject list |
| `app/web/look_routes.py` | Settings → Tags and Settings → Themes |
| `app/web/engine_routes.py` | Settings → Search Engines (on / off, status, Test Now, recent searches) |
| `app/web/backup_routes.py` | Settings → Backups |
| `app/web/people_routes.py` | People: users, roles, login history, My Password |
| `app/web/help_routes.py` | Help Center, Developer Tools, Handbook |
| `app/web/filters.py` | Filter chips (incl. Tag) |
| `app/templates/` | Pages (`base.html` shell, `_sidebar.html`, `_bigcard.html`, `contacts.html` …) |
| `app/static/app.css` | All styles; colours are CSS variables set by the theme |
| `backup/run.sh` | The backup loop (runs in the `backup` container) |
| `renderer/` | The Chromium renderer container |
| `netgate` | The server command (`update`, `rollback`, `versions`, `backup`, `restore` …) |
| `tests/` | End-to-end tests (`test_v05.py` … `test_v09.py`) and fake websites |

**Adding a page:** route in a `*_routes.py` with `render(..., help="slug")`, a template, a help page in `app/help/`, a Handbook feature page if it is a new feature, and a line in the test.
