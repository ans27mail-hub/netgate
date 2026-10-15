# NetGate

Ask your local AI to search and crawl the web, then add or update what it finds in a knowledge base.

**Stack:** Python 3.12 · FastAPI · Jinja2 + HTMX + Tabler · PostgreSQL · Redis + RQ · SearXNG · Ollama (on the iMac)

```
Browser ──► web (FastAPI) ──► Redis queue ──► worker
                                              ├─► SearXNG (search)
                                              ├─► fetch + Trafilatura (clean text)
                                              ├─► Ollama on the iMac (extract JSON)
                                              └─► Postgres (upsert by source URL)
```

## Server commands (WSL)

| Command | What it does |
|---|---|
| `netgate update` | Get the latest version from GitHub and restart |
| `netgate rollback` | Go back to the previous version |
| `netgate rollback <ver>` | Go to a specific version |
| `netgate versions` | List recent versions |
| `netgate status` / `logs` / `restart` / `stop` / `start` | Day-to-day control |

App folder: `~/apps/netgate` · UI: http://localhost:8090 · Settings: `~/apps/netgate/.env`

## Fresh install (new machine)

```bash
git clone https://github.com/ans27mail-hub/netgate.git ~/apps/netgate
cd ~/apps/netgate
cp .env.example .env && nano .env      # set passwords, iMac IP, model
sudo ln -sf ~/apps/netgate/netgate /usr/local/bin/netgate
netgate update
```

## Ollama on the iMac

Ollama must accept network requests:
```bash
launchctl setenv OLLAMA_HOST 0.0.0.0:11434   # then quit and reopen Ollama
```
Recommended model for NetGate: `qwen3:8b`.
