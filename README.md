# NetGate

Ask your local AI to search and crawl the web, then add or update what it finds in a knowledge base.

**Stack:** Python 3.12 · FastAPI · Jinja2 + HTMX · PostgreSQL · Redis + RQ · SearXNG · Ollama (on the iMac)

```
Browser ──► web (FastAPI, login) ──► Redis queue ──► worker
                                                    ├─► SearXNG (search)
                                                    ├─► eBay Browse API (eBay search method)
                                                    ├─► fetch (polite: robots.txt, per-site delay, cache)
                                                    ├─► renderer (headless Chromium for JavaScript pages)
                                                    ├─► code-first extraction (email, phone, WhatsApp, social, schema.org)
                                                    ├─► Ollama on the iMac (fills the group's fields as JSON)
                                                    └─► Postgres → Inbox → accepted into directories
```

## How it works

1. **Search** — a keyword runs with the directory's search methods: Web search, Directory sites, or **eBay**.
2. **Read** — pages are read politely (robots.txt, delay, cache); JavaScript pages in a headless browser;
   next pages and directory profiles are followed.
3. **Pick out details** — code first (emails, phones, WhatsApp, social links, schema.org), then the AI for the rest.
4. **Inbox** — new companies wait until a person accepts them into one or more directories, or rejects them with
   a reason. NetGate suggests a decision from earlier ones.
5. **Enrich** — fills missing fields from the company's website, search results and eBay.
6. **Night jobs** — keywords and enriching run by themselves in a night window.

Everything is explained inside the app: **Help** (and the **?** on every page).
For developers and AI assistants: start with **[AGENTS.md](AGENTS.md)**, then `docs/`.

## Organised as

- **Directories** (Manufacturers, Online retailers …): search methods, fields (with “Filled from”), keywords and
  AI instructions per directory. One contact can be in several directories.
- **Dashboard** (start page), **Directories** page (cards), **Inbox**, **All contacts** (filters + saved views),
  **Requests** (pause, stop, delete, reject, run again). Contacts can be moved between directories.
- **People**: users (reset password, switch off, delete, login history) and **roles** (Admin, Manager, Researcher,
  Viewer, Developer + your own) with a permission grid; directory access per person.
- **Settings**: AI servers & models, night jobs, crawler, connections (eBay / Etsy keys), reject list, display.
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
