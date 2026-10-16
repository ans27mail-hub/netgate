# NetGate

Ask your local AI to search and crawl the web, then add or update what it finds in a knowledge base.

**Stack:** Python 3.12 · FastAPI · Jinja2 + HTMX · PostgreSQL · Redis + RQ · SearXNG · Ollama (on the iMac)

```
Browser ──► web (FastAPI, login) ──► Redis queue ──► worker
                                                    ├─► SearXNG (search)
                                                    ├─► fetch (polite: robots.txt, per-site delay, cache)
                                                    ├─► renderer (headless Chromium for JavaScript pages)
                                                    ├─► code-first extraction (email, phone, WhatsApp, social, schema.org)
                                                    ├─► Ollama on the iMac (fills the group's fields as JSON)
                                                    └─► Postgres (add or update by group + source URL)
```

## How it works

1. **Discover** — a keyword (or "+ Find companies") searches the web in a few variations, reads list pages and
   company pages, and adds every matching company with name, city, country and website.
2. **Enrich** — the update icon on a company searches for that company by name and city, reads its own website
   (home, About, Contact), uses each field's search words, finds Facebook / Instagram / LinkedIn links, and fills
   only the missing fields. Each run uses what is already known, so the next run is more precise.
3. **Night jobs** — inside a time window (e.g. 11 pm – 7 am) NetGate discovers with the night keywords, then
   enriches incomplete companies (least complete first) and refreshes old ones. It stops by itself when the window ends.

## Crawler (v0.4)

- **Real browser** — pages that need JavaScript are opened in a headless Chromium (the `renderer` container).
  Mode: auto / always / never, plus a list of sites that always use it.
- **Next pages** — list pages are followed to page 2, 3, … (limit in Settings → Crawler).
- **Directory mode** — on directory sites NetGate opens each company's profile page to get its real website,
  email and phone.
- **Code first** — emails (incl. hidden Cloudflare ones), phones, WhatsApp, social links and schema.org company data
  are read by code; the AI is only asked for what code could not find.
- **Wider site reading** — Contact, About, Impressum pages from links and the sitemap.
- **Long pages** are split into chunks so nothing is cut off.
- **Cache** — pages are kept for a few days, so repeat runs are fast.
- **Polite** — respects robots.txt, waits between requests to the same site, retries once.

Settings → **Connections** stores API keys for eBay (UK, DE, IT, FR, US, CA …) and Etsy, ready for the marketplace
search methods coming in a later version.

## How it is organised

- **Groups** (Manufacturers, Materials, …) are the directory tabs. Admins create them in Settings.
- Each group has **keywords** (click one to make the AI search and update that group) and
  **fields** (City, Products, Employees, …) that the AI fills and that can be used to filter, sort and show on cards.
- **Users** log in. Each user has permissions (view, request, keyword updates, edit, delete, manage groups,
  manage users) and can be limited to selected groups. Admins can do everything.
- The first time NetGate starts with no users, it shows a page to create the first admin.
- Each group has its own AI instructions (what belongs, how to fill fields, what to ignore) and a page tester.
- AI servers (Ollama on the iMac, a GPU PC later, optional OpenRouter with spending limits) and the model per job
  are chosen in Settings → AI servers.
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
