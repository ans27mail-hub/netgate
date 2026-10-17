---
title: Backups
order: 105
updated: v0.7
---
**What it does:** a full database backup every night (time and how many days to keep are set in Settings → Backups), **Back Up Now**, download, and a Dashboard warning when the last backup is older than 2 days (or none, or switched off). Restore only on the server: `netgate restore`.

## How it works
- Container **`backup`** (image `postgres:16-alpine`, so `pg_dump` matches the database) runs `backup/run.sh`: every minute it reads `app_settings` (`backups`, `backups.request`), makes `netgate-YYYYMMDD-HHMM.dump` (pg_dump custom format) in `/backups` when it's time or asked, deletes old ones, and writes `backups.status`.
- The folder is `BACKUP_DIR` from `.env` (default `./backups`); the `web` container mounts it read-only for the list and downloads.
- `netgate backup` makes one from the command line; `netgate restore <file>` asks for RESTORE, saves a safety copy first, stops the app containers, runs `pg_restore --clean`, starts them again.

## Files
`backup/run.sh`, `app/backups.py`, `app/web/backup_routes.py`, `templates/backups.html`, `netgate`, `docker-compose.yml`.

## Permissions
*Backups* (Admin by default).
