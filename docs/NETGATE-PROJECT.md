# NetGate — Complete Project Document

As of 18 Oct 2026 · Owner: Abdul Moeez (Motofast International, Sialkot)

Same content as the owner's "NetGate — Complete Project Document" in Claude. Keep both up to date when the project changes.

## What NetGate Is

NetGate is Motofast's own business-directory builder: it searches the web with a local AI and collects companies (manufacturers, suppliers, retailers, marketplace sellers) into directories that people review and use.

- **Owner:** Abdul Moeez, Motofast International, Sialkot.
- **Who uses it:** the owner and admins; researchers who run searches and review results; viewers; developers who improve it.
- **The idea:** search finds companies → people accept the good ones in an Inbox → NetGate fills the missing details (Enrich) → clean, filterable directories that can be exported.
- **Where it runs:** on the owner's Windows PC, in Docker inside WSL. The AI (Ollama, model qwen3:8b) runs on the owner's iMac.
- **Where the code lives:** the GitHub repository `ans27mail-hub/netgate` (private). The owner installs every new version with one command, `netgate update`.
- **Everything stays in one app:** page saving and scans will be part of NetGate, not a separate app (owner decision, 18 Oct 2026).

## Current Status

NetGate is at **v0.7** (released 17 Oct 2026). v0.8 is agreed as a list and waits for “build v0.8”.

| Version | Date | What it brought |
| --- | --- | --- |
| v0.7 | 17 Oct 2026 | Tags, card styles A/B/C and fixed card width, Short Card Shows, themes (incl. Dark), bigger Help window, Debug actions, what each person sees (own contacts, own/selected directories, search methods hidden), Existing Contacts tab, Title Case, Developer Handbook, automatic backups, Running Jobs on the Dashboard |
| v0.6 | 16 Oct 2026 | Dashboard start page, Directories page, directory switcher, moving contacts, People (users, reset password, login history, roles copy / rename / delete) |
| v0.5 | 16 Oct 2026 | Left-sidebar layout, Discovery Inbox, one contact in many directories, search methods per directory incl. eBay API, add contacts by hand, request controls, roles and permissions, Help Center, AI suggestions from decisions |
| v0.4 | 16 Oct 2026 | Crawler upgrade: Chromium browser for JavaScript pages, next pages, code-first contact finding, sitemap, cache, polite limits, Connections settings |
| v0.3 | 15 Oct 2026 | Discover + Enrich, night jobs, AI server per job, compact and big cards, list view |
| v0.2 | 15 Oct 2026 | Login, users, permissions, groups with keywords and fields |
| v0.1 | 15 Oct 2026 | Starter: search, crawl, save with the local AI, Docker setup, `netgate` command |

## What NetGate Does Today

Every page has a **?** button that opens its help.

| Area | What you can do |
| --- | --- |
| Dashboard | Numbers at a glance, Needs Attention (with a button each), Running Jobs, Quick Actions, System status (AI server, browser, search engine, eBay), Directories table, recent activity |
| Directories | One card per directory; tabs and Jump To to switch; Contacts and Existing Contacts tabs; complete bar; Find New, Run All Keywords, Enrich All Incomplete |
| Directory Settings | Name, owner, search words, search methods, Cards (style A/B/C, width, tint), fields (type, Filled from, Find / Enrich step, search words), AI instructions, keywords with night runs, Test a Page, Delete |
| Contacts | Grid or list, filters and saved views, sort, tags, Export CSV; big card with Edit, Enrich Now, Short Card Shows, + Tag, Move Here / Also Add Here, Delete |
| Inbox | New / Enriched / Rejected tabs, AI suggestions, accept into any directory, reject with a reason, restore |
| Add Contact | One contact, a pasted list or a CSV; duplicate check; choose Enrich steps; now, tonight or Inbox only |
| Requests | Every search and enrich job; Pause, Resume, Stop, Delete (30-day bin), Reject keyword, Run Again; Debug page per request |
| People | Users, roles and permissions, what each person sees, reset password, login history |
| Settings | Tags, Themes, Backups, AI Servers & Models, Night Jobs, Crawler, Connections (API keys), Reject List, Display, My Password |
| Help & Developer Tools | Help Center with Ask NetGate, What's New; Debug, Logs, Page Tester, Training Data, Developer Handbook |

## How It Works

Nothing reaches a directory until a person accepts it in the Inbox.

```
1. Keyword or request  →  2. Search (SearXNG: Google, DuckDuckGo…; eBay API; B2B directory sites)
   →  3. Crawler reads pages (Chromium for JavaScript pages, next pages, Contact, About)
   →  4. Code first, then the AI (code: emails, phones, links; AI on the iMac: which company, does it fit?)
   →  5. Inbox (a person accepts or rejects; rejects teach the suggestions)
   →  6. Directory (each company stored once, can sit in several directories)
   →  7. Enrich (fills missing fields from its website, social and other pages)
   →  8. Ready to use (filter, tag, export CSV; night jobs keep it growing)
```

A search turns a keyword into Inbox suggestions; only what a person accepts enters a directory, where Enrich fills the gaps. Plain code finds emails, phones and links; the local AI only judges what code can't, such as which company a page is about and whether it fits the directory's instructions. SearXNG is the weak point today (search engines block automated searches), which v0.8 points 3, 4, 5 and 7 address.

## People, Roles and What Each Person Sees

Each person has a role; a person can get their own exceptions on top of it (shown with a “custom” badge). Admins can always do everything.

| Role | Typical use | Default access |
| --- | --- | --- |
| Admin | Owner | Everything, locked |
| Manager | Runs the directories | Contacts, searching, Inbox, directories, tags; sees search methods |
| Researcher | Runs searches and reviews | View, export, add, run discovery and keywords, enrich, Inbox; does not see search methods |
| Viewer | Looks things up | View and export |
| Developer | Improves NetGate | Debug, logs, page tester, training data, Developer Handbook; sees search methods |

Per person (People → a user → What This Person Sees):

- **Directories:** all, only selected ones, or only their own (directories they created or own).
- **Contacts:** all, or only their own (the ones they found first or added).
- **Existing Contacts:** when their search finds a company someone else found first, it shows in that directory's Existing Contacts tab. The first finder stays. They see the full card or only chosen fields.
- **Permissions:** See search methods; Enrich other people's contacts; Developer help (Handbook), and the rest of the permission grid.

## Server Setup and Commands

NetGate lives in `~/apps/netgate` in WSL and opens at http://localhost:8090. Its settings file is `~/apps/netgate/.env`.

Fresh install on a new machine:

```bash
git clone https://github.com/ans27mail-hub/netgate.git ~/apps/netgate
cd ~/apps/netgate
cp .env.example .env && nano .env      # passwords, iMac IP, model
sudo ln -sf ~/apps/netgate/netgate /usr/local/bin/netgate
netgate update
```

On the iMac, Ollama must accept network requests: `launchctl setenv OLLAMA_HOST 0.0.0.0:11434`, then quit and reopen Ollama.

| Command | What it does |
| --- | --- |
| `netgate update` | Installs the newest version from GitHub and restarts |
| `netgate rollback` | Goes back one version (or `netgate rollback v0.6` for a chosen one) |
| `netgate versions` / `netgate version` | Lists the versions / shows the one installed |
| `netgate backup` | Makes a database backup now |
| `netgate restore` | Lists backups; `netgate restore <file>` puts one back after a safety copy (server only) |
| `netgate status` / `logs` | Shows the containers / follows the app's log |
| `netgate restart` / `stop` / `start` | Restarts, stops or starts NetGate |

Important `.env` lines: `POSTGRES_PASSWORD`, `DATABASE_URL`, `OLLAMA_URL` (the iMac's address, e.g. http://192.168.33.17:11434), `MODEL=qwen3:8b`, `MAX_PAGES`, `ENRICH_PAGES`, and optional `BACKUP_DIR` (best on another disk, e.g. `/mnt/d/netgate-backups`).

Containers: `web` (pages), `worker` and `night-worker` (searches), `scheduler` (night runs and clean-up), `db` (Postgres), `redis` (job queue), `renderer` (Chromium for JavaScript pages), `searxng` (search engine), `backup` (nightly backups). If the repository is private, the PC needs a read-only GitHub token saved once with `git config credential.helper store`.

## Next Update List (v0.8)

Nine points are agreed; nothing is built until the owner says “build v0.8”. Splitting it into v0.8 (points 2, 5–9) and v0.9 (points 1, 3, 4) is offered. Details: `docs/ROADMAP.md`.

| # | Point | What it means | Status |
| --- | --- | --- | --- |
| 1 | Verify and Company page | Every value keeps where it came from; Verify re-checks it; short company profile; products as their own records | Agreed |
| 2 | Delete only empty directories | Delete is off while a directory has contacts; Inbox items waiting for it are removed with it after a warning | Agreed |
| 3 | Search Engines settings | Turn engines on or off, see which work or block, backup search keys (Brave, Google, Serper — prices checked first), engine shown in Debug | Waiting for OK |
| 4 | Browser search | Chromium opens Bing / DuckDuckGo (Google only if switched on), keeps going until enough matches; pauses, hourly limit, stops on a CAPTCHA | Agreed |
| 5 | List of pages read | Permanent record of every page read; Enrich and discovery don't read the same pages again; start of Saved Pages | Agreed |
| 6 | Edit and Run Again | Change a finished request and run it again in the same request; history of tries, Go Deeper, Save as Keyword | Agreed |
| 7 | Stronger Enrich searching | Searches built from what is known; own Enrich search words per directory and per contact; steps and depth per directory; each search in Debug | Agreed |
| 8 | Moving between directories | Preview of hidden / missing details, Other Details on the big card, Same As to link fields with different names | Agreed |
| 9 | Contact cards fill the row | Card width becomes a minimum; with Fill the row (on by default) cards stretch evenly to the full width, never narrower than the set width | Agreed |

## Longer-Term Plan

After v0.8 the agreed order is below; each step is explained first and built only on “build”.

1. **Saved Pages & Scans, inside NetGate.** Save single pages and whole sites (manual and automatic), keep versions, recipes per site, a page library and storage rules. Heavy scans run in their own worker container in the same setup; pages are stored in a folder set in `.env`.
2. **Chrome extension.** Connects to NetGate with a key from Settings → Connections: Save Page, auto-capture on chosen sites, a never-capture list.
3. **Sources list, products and image cache.** Every website used, with its type, value, last use and whether it needs a login. Product images are kept as links and fetched only when a Company page is viewed, then deleted after X days unless “Keep images” is on. Internal use only.
4. **User Wallet (one login for all factory apps) with Authentik.** Each app can switch between its own login, Authentik or both without code changes; admin accounts always stay in the app. **Vaultwarden** keeps passwords for outside websites.

Other ideas, not scheduled: Etsy search, Amazon sellers, custom recipes per site, pictures on cards, watch lists and alerts, a test directory for developers, an “Items, not companies” directory type.

## Key Decisions and Rules

How work is done:

- Explain or show a mockup first; build only when the owner says “build”. Versions are v0.1, v0.2 …; every version installs with `netgate update`.
- Each release updates the roadmap, decisions and What's New, and adds a line to `releases.txt`.
- Plain English everywhere; headings, menus, tabs and buttons in Title Case.

How NetGate behaves:

- **Nothing reaches a directory without being accepted** in the Inbox (unless someone allowed to review ticks “accept straight away”).
- **A company is stored once** and can be in several directories; each directory only decides which fields it shows and looks for. Moving keeps every detail.
- **Code first, AI second:** emails, phones, links and similar are found by plain code; the AI is asked only for the rest.
- **Requests are separate from contacts:** deleting or rejecting a request never changes contacts.
- **The first finder keeps a contact;** later finds by others show in Existing Contacts.
- **Search methods and site recipes are code**, changed only through GitHub, never in the web pages.
- **Secrets are never shown back** on a page; the Handbook never contains passwords or keys.
- **Restoring a backup is only possible on the server**, never from the web page.
- **Polite crawling:** robots.txt, a pause per site, one retry; CAPTCHAs are never solved.
- **One app:** page saving and scans stay inside NetGate (changed 18 Oct 2026 from a separate Scanner app).
- **Logins later:** Authentik for all factory apps with a per-app switch back to the app's own login; Vaultwarden for outside passwords.

Full list with reasons: `docs/DECISIONS.md`.

## Where Everything Is

| File or place | What it holds |
| --- | --- |
| `AGENTS.md` | Start here: rules for any AI or developer continuing the project |
| `docs/NETGATE-PROJECT.md` | This document |
| `docs/PROJECT.md` | Purpose, users, the owner's setup |
| `docs/ROADMAP.md` | What is done per version and the agreed next steps |
| `docs/DECISIONS.md` | Choices made and why |
| `docs/ARCHITECTURE.md` | How the code fits together |
| `docs/DESIGN.md` + `docs/design/` | Layout direction and screenshots |
| `CHANGELOG.md` | What's New per version (also in the app under Help) |
| `releases.txt` | Version list used by `netgate update`, `rollback`, `versions` |
| `app/help/` | The in-app Help pages |
| `docs/dev/` | The Developer Handbook (also in the app under Developer Tools) |
| `tests/` | The end-to-end tests run before each release |

To continue in a new chat session, paste: “Read AGENTS.md in github.com/ans27mail-hub/netgate and continue the project. Next: v0.8.”
