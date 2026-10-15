# NetGate

Ask your local AI to search and crawl the web, then add or update what it finds in a knowledge base.

**Stack:** Python 3.12 · FastAPI · Jinja2 + HTMX · PostgreSQL · Redis + RQ · SearXNG · Ollama (on the iMac)

```
Browser ──► web (FastAPI, login) ──► Redis queue ──► worker
                                                    ├─► SearXNG (search)
                                                    ├─► fetch + Trafilatura (clean text)
                                                    ├─► Ollama on the iMac (fills the group's fields as JSON)
                                                    └─► Postgres (add or update by group + source URL)
```

## How it is organised

- **Groups** (Manufacturers, Materials, …) are the directory tabs. Admins create them in Settings.
- Each group has **keywords** (click one to make the AI search and update that group) and
  **fields** (City, Products, Employees, …) that the AI fills and that can be used to filter, sort and show on cards.
- **Users** log in. Each user has permissions (view, request, keyword updates, edit, delete, manage groups,
  manage users) and can be limited to selected groups. Admins can do everything.
- The first time NetGate starts with no users, it shows a page to create the first admin.
- Database changes are applied automatically at start-up and keep existing data.

## Server commands (WSL)

| Command | What it does |
|---|---|
| `netgate update` | Get the latest version from GitHub and restart |
| `netgate rollback` | Go back to the previous version |
| `netgate rollback v0.1` | Go to a specific version |
| `netgate versions` | List all versions (v0.1, v0.2, …) |
| `netgate version` | Show the version running now |
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
