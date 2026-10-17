---
title: Database — what the tables mean
order: 50
updated: v0.7
---
The full list of tables and columns is on [Database tables (automatic)](/dev/handbook/auto-database). This page explains them.

- **`groups`** — directories. `methods` (JSON: which search methods and their options), instructions for the AI, `owner_id` (for “own directories”), `card` (style A/B/C, width, tint).
- **`fields`** — the fields of a directory (City, Employees …): type, “Filled from” (`source`), step (find / enrich), shown on card / list, filter / sort.
- **`keywords`** — per directory; `method` (all or one), night on/off, last run, how many found.
- **`records`** — contacts, once each. `data` (field values, JSON), `sources` (where each value came from), `social`, `links` (store pages), `ext` (ids on other sites, e.g. eBay seller), `history` (plain-text notes), `notes`, `accepted_at`, `found_by` (first person who found or added it), `vec` (vector for suggestions).
- **`memberships`** — which contact is in which directory.
- **`inbox`** — one item per contact + directory waiting for a decision (new / accepted / rejected), with method, keyword, AI suggestion.
- **`decisions`** — every accept / reject / restore / remove / move with a snapshot of the contact (used for suggestions and training data).
- **`existing_hits`** — a person's search found a contact someone else found first (Existing Contacts tab).
- **`tags`**, **`record_tags`** — tags and which contact has which.
- **`jobs`** — requests: query, kind, status, `stats`, `params`, `control` (pause / stop asked), `state` (where a paused job got to), `deleted_at`.
- **`job_traces`** — debug notes per request (pages, code finds, AI questions), kept 14 days.
- **`rejected_keywords`** — the reject list.
- **`users`**, **`roles`**, **`user_groups`** — people, roles, selected directories. Users also have `contacts_scope`, `dir_scope`, `existing_view`, `existing_fields`, `must_change`, `last_login_at`.
- **`logins`** — login history (180 days; not linked by key, so it stays after a user is deleted).
- **`ai_servers`**, **`ai_usage`** — AI servers and OpenRouter cost log.
- **`night_runs`**, **`page_cache`**, **`app_log`**, **`app_settings`** (JSON settings + upgrade flags).

**Deleting rules:** deleting a contact removes its memberships, Inbox items, tags and existing hits; deleting a request never touches contacts (`records.job_id` is set to empty); deleting a user keeps everything they did (shown as “(deleted user)”).
