---
title: Upgrades, releases and rollback
order: 60
updated: v0.7
---
## How the owner updates
`netgate update` (bash script `netgate` in the repo, linked to `/usr/local/bin/netgate`):
`git fetch` → `git reset --hard origin/main` → `docker compose up -d --build` → prints the version.
`netgate rollback` goes back one release (from `releases.txt`), `netgate rollback v0.5` to a given one, `netgate versions` lists them.

## Database upgrades (keep data!)
At every start, `init_db()` (with Postgres advisory locks, because web and scheduler both start it):
1. `Base.metadata.create_all` — new tables.
2. Every statement in `MIGRATIONS` — must be **idempotent** (`ADD COLUMN IF NOT EXISTS` …).
3. One-time steps `_upgrade_v03`, `_upgrade_v05`, `_upgrade_v07` — each guarded by a flag in `app_settings` (`v07_upgraded` …).

Rollback works because new columns have defaults and old code ignores them. Never rename or drop a column; add a new one.

## Releasing a version
1. Tests pass (see [Testing](/dev/handbook/testing)); look at the main pages in a browser.
2. Update `docs/ROADMAP.md`, `docs/DECISIONS.md`, `CHANGELOG.md` (shown in the app as What's New) and this Handbook.
3. Commit; add `v0.x  <commit>  <YYYY-MM-DD>  <description>` as the first version line of `releases.txt` (below the two `#` lines); commit; push to `main`.
4. Tell the owner what to run (`netgate update`) and anything special.

## Private repository
The PC then needs a read-only GitHub token: `git config credential.helper store` and one `git fetch` (username + token as password).
