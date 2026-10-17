---
title: Containers, machines and what happens when one is down
order: 30
updated: v0.7
---
Everything is in `docker-compose.yml`, started by `netgate update` in `~/apps/netgate` (WSL on the owner's PC).

| Container | Does | If it is down |
|---|---|---|
| `web` | All pages (port **8090**). Runs the database upgrade at start. | NetGate can't be opened. Jobs already queued keep running. |
| `worker` | Discover and Enrich requests (queue `netgate`) | Requests wait in **Waiting** |
| `night-worker` | The night run (queue `netgate-night`) | The night run doesn't happen |
| `scheduler` | Starts the night run in its window; hourly clean-up (page cache, deleted requests after 30 days, traces 14 days, log 60 days, logins 180 days) | No night run, no clean-up |
| `db` | PostgreSQL 16 (volume `pgdata`) | Nothing works |
| `redis` | Job queue | Requests can't start |
| `renderer` | Headless Chromium (`/render`, `/health`) | Pages that need JavaScript are read without it (less found) |
| `searxng` | Search engine (port 8888, local only) | Web / directory searches find nothing |
| `backup` | Database backups at night + Back Up Now (`backup/run.sh`, postgres:16 tools) | No new backups (Dashboard warns after 2 days) |

**Outside Docker:** Ollama on the iMac (`OLLAMA_URL` in `.env`, e.g. `http://192.168.33.17:11434`). If the iMac sleeps, the AI steps fail (requests fail with an AI error; the Dashboard → System shows *offline*).

**`.env`** holds `POSTGRES_PASSWORD`, `APP_SECRET_KEY`, `SEARXNG_SECRET`, `OLLAMA_URL`, optional `BACKUP_DIR` and `TZ`. Everything else is set in the app.

Logs: NetGate's own log is in Developer Tools → Logs; container logs in WSL: `docker compose logs --tail 100 <container>`.
