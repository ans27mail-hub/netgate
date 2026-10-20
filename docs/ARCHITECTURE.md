# Architecture

## Containers (`docker-compose.yml`)
| Service | Image / command | Role |
|---|---|---|
| `web` | `uvicorn app.main:app` (port 8090 → 8000) | All pages. Runs database upgrades at start-up. |
| `worker` | `python -m app.worker netgate` → `rq worker netgate` | Discover and Enrich requests (v0.9: at start, marks its leftover running requests Interrupted and re-queues waiting ones) |
| `night-worker` | `python -m app.worker netgate-night` | The night run (so daytime jobs don't wait) |
| `scheduler` | `python -m app.scheduler` | Starts the night run in its window; every minute: requests with no progress for 30 min → Interrupted; hourly: purge page cache, deleted requests (30 d), traces (14 d), log (60 d) |
| `db` | postgres:16-alpine | Data (volume `pgdata`) |
| `redis` | redis:7-alpine | Job queue |
| `renderer` | `renderer/` Playwright Chromium, `GET /render?url=` | Pages that need JavaScript |
| `searxng` | searxng/searxng | Search engine (port 8888 on localhost) |
| `backup` | postgres:16-alpine running `backup/run.sh` | Every minute reads Settings → Backups; makes `pg_dump` files in `BACKUP_DIR` (web mounts it read-only) |

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
| `tags.py` | Tags: list, usable in a directory, set / add / remove, card tint |
| `themes.py` | Built-in and custom themes → CSS variables, fonts, contrast warnings |
| `backups.py` | Backup settings, status, files, “Back Up Now” request (the `backup` container does the work) |
| `handbook.py` + `docs/dev/` | Developer Handbook: written pages, feature list (test enforced), automatic pages from the code |
| `web/look_routes.py`, `web/backup_routes.py` | Settings → Tags, Themes, Backups |
| `pages.py` | v0.9: the list of pages read — record, skip list pages read before, reuse a company's pages |
| `worker.py` | v0.9: worker start-up (tidy leftover requests), then `rq worker` |
| `engines.py`, `web/engine_routes.py` | v0.8: Settings → Search Engines — chosen SearXNG engines, `search_log`, status per engine |

## Main tables
`groups` (= directories, with `methods` JSON), `fields` (`source` = Filled from), `keywords` (`method`), `records` (contacts: `data`, `sources`, `social`, `links`, `ext`, `history`, `notes`, `accepted_at`, `vec`), `memberships` (contact ↔ directory), `inbox` (InboxItem: per contact + directory, status new / accepted / rejected, suggestion), `tags`, `record_tags`, `existing_hits` (v0.7: a person's search found a contact someone else found first), `decisions` (every accept / reject with a snapshot), `jobs` (requests: `control`, `state`, `params`, `deleted_at`), `job_traces` (debug), `rejected_keywords`, `roles`, `users` (`role_id`, `extra_perms`, `removed_perms`, `must_change`, `last_login_at`), `logins` (login history, not linked by FK so it survives deleting a user), `user_groups`, `ai_servers`, `ai_usage`, `night_runs`, `page_cache`, `app_settings` (JSON settings + upgrade flags), `app_log`, `search_log` (v0.8: one row per web search, links / failures per engine), `pages_read` (v0.9: every page read and what was found), `font_files` (v0.9: uploaded fonts).

## How a search runs
1. A page calls `start_job()` → a `jobs` row + an RQ job → the worker runs `jobs.run_job(id)`.
2. `run_job` skips paused / stopped / deleted jobs and rejected keywords, then `discover()` runs each chosen method:
   - **web**: search variations → page queue → `crawl_pages()`; **directory**: list pages / `site:` searches → `crawl_pages()` with profiles on; **ebay**: `ebay.find_sellers()`.
   - `crawl_pages()`: download (cache, robots, delay, renderer) → AI lists entries (chunks) → code-first details from the page or profile pages → `save_entry()` → `contacts.upsert()` + `contacts.to_inbox()` → suggestions scored (`learn.score_items`). List pages put their next page at the front of the queue.
3. `Ctx.check()` reads `jobs.control` (every 2 s at most). *pause* → the current page is put back in the queue, state saved in `jobs.state`, status `paused`; Resume re-queues it and `discover()` continues from the state. *stop* → status `stopped` (or `rejected`).
4. Every search (with the engine of each link), page, code find and AI question / answer is written to `job_traces` (Debug view). Every web search also goes to `search_log`.
5. **Edit and Run Again** (v0.8): `control.edit_and_run()` stores the finished try in `jobs.params.tries`, changes query / directory / methods / `deeper` and re-queues the same job.

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
- `tests/test_v07.py` — v0.6 → v0.7 upgrade: tags, card styles, short-card fields, themes, debug clear, own / selected / own-directory scopes, search methods hidden, Existing Contacts (limited view, enrich permission), Handbook (every feature has a page), backups settings and files, Running Jobs.
- `tests/test_v09.py` — v0.8 → v0.9: stuck requests, pages read (Discover skip, earlier tries, Enrich reuse, Check All Again), stronger Enrich + Directory Settings → Enrich, Enrich Now ▾, new permissions + Cards Only, colour sets / fonts / uploaded fonts / My Look, pop-up script.
- `tests/test_v08.py` — v0.7 → v0.8: delete only empty directories, Fill the row, Edit and Run Again (tries, Go Deeper, Save as Keyword, permissions), Search Engines with a fake SearXNG (`tests/fake_searx.py`).
- After a change, also open the main pages in a browser (the test does GET requests; screenshots catch layout problems).


More detail for developers is in the **Developer Handbook** (`docs/dev/`, also in the app under Developer Tools).
