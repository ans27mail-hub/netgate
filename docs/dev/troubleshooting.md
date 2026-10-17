---
title: Troubleshooting (symptom → cause → fix)
order: 80
updated: v0.7
---
| Symptom | Likely cause | Fix |
|---|---|---|
| Dashboard → System: **AI server offline** | iMac asleep, Ollama not running, wrong `OLLAMA_URL` | Wake the iMac; `ollama serve`; check the address in `.env`; Settings → AI → Test |
| Searches find **nothing** | SearXNG down or rate-limited by public engines | `docker compose logs searxng`; wait, or change engines in `searxng/settings.yml` |
| A site's companies are **missing** | Page needs JavaScript, robots.txt forbids, or the site blocks robots | Debug view of the request; Settings → Crawler → “always use the browser” for that site |
| **Browser (renderer) offline** | Container crashed (memory) | `docker compose restart renderer`; it is memory-capped at 1.5 GB |
| Requests stay **Waiting** | `worker` container stopped | `docker compose ps`; `docker compose up -d` |
| No **night run** | Night jobs off, outside the window, or `scheduler` / `night-worker` down | Settings → Night Jobs; `docker compose ps` |
| **Backup** warning on the Dashboard | `backup` container stopped, or folder not writable | `docker compose logs backup`; check `BACKUP_DIR` in `.env` |
| “Something went wrong on this page” | A code error | Developer Tools → Logs shows the error and where |
| Someone can't see a contact | Their directory access, “only own contacts”, or role | People → the user → What This Person Sees |
| eBay search finds nothing | Keys missing / wrong, or business-only filter | Settings → Connections → Save & Test eBay Keys |
| Disk full | Page cache, backups, Docker images | Settings → Crawler (cache days), Settings → Backups (keep days), `docker image prune` |
