# Architecture

## Containers (`docker-compose.yml`)
| Service | Image / command | Role |
|---|---|---|
| `web` | `uvicorn app.main:app` (port 8090 → 8000) | All pages. Runs database upgrades at start-up. |
| `worker` | `rq worker netgate` | Discover and Enrich requests |
| `night-worker` | `rq worker netgate-night` | The night run (so daytime jobs don't wait) |
| `scheduler` | `python -m app.scheduler` | Starts the night run in its window; hourly: purge page cache, deleted requests (30 d), traces (14 d), log (60 d) |
| `db` | postgres:16-alpine | Data (volume `pgdata`) |
| `redis` | redis:7-alpine | Job queue |
| `renderer` | `renderer/` Playwright Chromium, `GET /render?url=` | Pages that need JavaScript |
| `searxng` | searxng/searxng | Search engine (port 8888 on localhost) |

Ollama (the AI) runs outside Docker, on the iMac. `.env` holds passwords and `OLLAMA_URL`; everything else is set in the app.

## Code map (`app/`)
| File | What |
|---|---|
| `main.py` | Creates the FastAPI app, includes the routers, error handlers |
| `web/common.py` | Templates, login, `require()`, sidebar data, `render()`, `start_job()` |
| `web/*_routes.py` | Pages: `dashboard` (Dashboard start page, system status, Directories page), `inbox`, `contacts` (All contacts, directory page, card, export, saved views), `add` (add contact), `requests` (controls, debug, starting searches), `settings` (directories, AI, night, display, crawler, connections, reject list), `people` (users, roles, login history, my password), `help` (Help Center + Developer tools), `auth` |
| `web/filters.py` | Filter chips: parse the query string, apply in SQL, build chips |
| `templates/` | Jinja2 + HTMX. `base.html` (shell), `_sidebar.html`, `_dirswitch.html` (directory tabs), `_people_tabs.html`, `_filters.html`, `_bigcard.html`, `_table.html` … |
| `static/app.css` | All styles (design tokens at the top; v0.5 layout at the end) |
| `db.py` | SQLAlchemy models, `MIGRATIONS`, one-time upgrades (`_upgrade_v03`, `_upgrade_v05`), seeding, `log()` |
| `auth.py` | Permission list (`PERM_GROUPS`), default roles, `can()`, password hashing |
| `contacts.py` | Matching, `upsert`, `to_inbox`, accept / reject / restore, memberships, `move`, history |
| `jobs.py` | `run_job` (entry point), `Ctx` (progress, pause/stop checks, debug trace), Discover per method, Enrich steps, night run |
| `methods.py` | Search method registry, field “Filled from” sources, enrich steps, connections (API keys) |
| `ebay.py` | eBay Browse API client: token, search, item, seller info, field mapping |
| `crawl.py` | Search, polite download, renderer, cache, links, next page, sitemap |
| `extract.py` | Code-first extraction: emails, phones, WhatsApp, social, schema.org |
| `ai.py` | Ollama / OpenRouter calls, `ask_json(job_type, prompt)`, model per job |
| `learn.py` | Vectors (word hashes or embeddings), Inbox suggestions, training export |
| `control.py` | Request actions (pause, resume, stop, delete, reject, run again), reject list, queues |
| `help.py` + `help/*.md` | Help Center pages and Ask NetGate |
| `scheduler.py` | Night window + hourly cleanup |

## Main tables
`groups` (= directories, with `methods` JSON), `fields` (`source` = Filled from), `keywords` (`method`), `records` (contacts: `data`, `sources`, `social`, `links`, `ext`, `history`, `notes`, `accepted_at`, `vec`), `memberships` (contact ↔ directory), `inbox` (InboxItem: per contact + directory, status new / accepted / rejected, suggestion), `decisions` (every accept / reject with a snapshot), `jobs` (requests: `control`, `state`, `params`, `deleted_at`), `job_traces` (debug), `rejected_keywords`, `roles`, `users` (`role_id`, `extra_perms`, `removed_perms`, `must_change`, `last_login_at`), `logins` (login history, not linked by FK so it survives deleting a user), `user_groups`, `ai_servers`, `ai_usage`, `night_runs`, `page_cache`, `app_settings` (JSON settings + upgrade flags), `app_log`.

## How a search runs
1. A page calls `start_job()` → a `jobs` row + an RQ job → the worker runs `jobs.run_job(id)`.
2. `run_job` skips paused / stopped / deleted jobs and rejected keywords, then `discover()` runs each chosen method:
   - **web**: search variations → page queue → `crawl_pages()`; **directory**: list pages / `site:` searches → `crawl_pages()` with profiles on; **ebay**: `ebay.find_sellers()`.
   - `crawl_pages()`: download (cache, robots, delay, renderer) → AI lists entries (chunks) → code-first details from the page or profile pages → `save_entry()` → `contacts.upsert()` + `contacts.to_inbox()` → suggestions scored (`learn.score_items`). List pages put their next page at the front of the queue.
3. `Ctx.check()` reads `jobs.control` (every 2 s at most). *pause* → the current page is put back in the queue, state saved in `jobs.state`, status `paused`; Resume re-queues it and `discover()` continues from the state. *stop* → status `stopped` (or `rejected`).
4. Every search, page, code find and AI question / answer is written to `job_traces` (Debug view).

## Enrich
`enrich(record_id, steps)` uses the fields of all directories the contact is in (or is waiting for): eBay store lookup → own website (home + Contact / About / Impressum / sitemap; code first, then AI on missing fields only) → searches → other pages → search snippets. Only empty fields are filled; sources recorded per field.

## Permissions
Login: the session stores a short tag of the password hash; when the password changes (reset or My password) other sessions are logged out. `must_change` sends the person to `/account/password` before any other page.

`can(user, perm, group_id)`: admins can do everything; otherwise the perm must be in the user's set (role + extras − removals). Directory permissions (`DIR_PERMS`) also need access to that directory (all, or the ticked ones).

## Updates
`netgate update` (bash script `netgate`): `git fetch`, `git reset --hard origin/main`, `docker compose up -d --build`. `releases.txt` lists versions for `netgate versions` / `rollback`. When the repository is private, the PC needs a read-only GitHub token saved once with `git config credential.helper store` and a `git fetch` (username + token as password).

## Testing
There is no pip access in the AI's build environment, so libraries were cloned from GitHub; the tests run against a real local Postgres, a fake website (`tests/fakeweb.py`), a fake eBay API (`tests/fake_ebay.py`) and the real renderer. The search engine and the AI are simulated inside the test. See `tests/README.md`.
- `tests/test_v05.py` — the full flow: v0.4 → v0.5 upgrade, Discover → Inbox, accept / reject / restore, multiple directories, suggestions, eBay, pause / resume / stop / reject / delete, add contact (one / list / CSV), roles, help, night run.
- `tests/test_v06.py` — v0.5 → v0.6 upgrade: Dashboard, Directories page, switcher, moving contacts (one / many / from all), People (add with must-change, reset logs out, disable, login history, delete keeps data, roles copy / delete with move).
- After a change, also open the main pages in a browser (the test does GET requests; screenshots catch layout problems).
