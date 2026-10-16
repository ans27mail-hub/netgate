# Roadmap

Update this file at the end of every work session.

## Done

### v0.1 — starter (15 Oct 2026)
Search (SearXNG), crawl, save with the local AI (Ollama). Docker setup, `netgate` command.

### v0.2 — login and groups (15 Oct 2026)
Login, users, permissions, per-group access; groups with keywords and fields; design “D” directory layout.

### v0.3 — Discover + Enrich (15 Oct 2026)
Discover (find companies: name, city, country, website) and Enrich (fill missing fields, social links); night jobs with a time window; AI servers per job (Ollama, OpenRouter with spending limits, fallback); compact cards + big card, list view with columns, display width (fixed / % / full).

### v0.4 — crawler upgrade (16 Oct 2026)
Headless Chromium renderer container; next-page following; directory profiles; code-first extraction (emails incl. Cloudflare-hidden, phones, WhatsApp, social, schema.org); sitemap and useful pages; chunking long pages; page cache; robots.txt, per-site delay, retry; Settings → Crawler and Settings → Connections (eBay/Etsy keys).

### v0.5 — Inbox, directories, roles, help (16 Oct 2026)
- Left-sidebar layout (D4 mockups): Inbox, All contacts, directories, saved views, Requests, Settings, Help, Developer tools.
- Discovery **Inbox** (New / Enriched / Rejected), accept into any directory, reject with reasons, restore list; rejected stays rejected for that directory.
- **One record, many directories** (memberships); groups became directories; v0.4 listings became accepted members.
- **All contacts** with filter chips and saved views; directory pages with method badges and complete bar.
- **Search methods** per directory: Web search, Directory site search, **eBay Browse API** (find sellers + store lookup), Company website; Etsy / Amazon / Custom recipe shown as “later”.
- Fields with **Filled from** (AI + code, website only, manual only, eBay values) and Step (Find / Enrich).
- **New directory** in five steps.
- **Add contact by hand** (one / paste list / CSV), duplicate check, enrich steps, now / tonight, accept straight away.
- Edit a contact by hand; notes go to the AI.
- **Learning:** decision log, similarity suggestions (word hashes; optional Ollama embeddings), training-data export (JSONL).
- **Request controls:** pause / resume (with saved state) / stop / delete (30-day bin) / reject (keyword reject list) / run again / bulk / pause all; status tabs.
- **Roles:** Admin, Manager, Researcher, Viewer, Developer; permission grid; per-person exceptions (“custom”); directory access per person with role default.
- **Developer tools:** debug trace per request, app log, page tester, training export.
- **Help Center** (Markdown pages in `app/help/`), “?” on every page, Ask NetGate (local AI), What's new.
- Handover docs: `AGENTS.md`, `docs/*`, `CHANGELOG.md`, tests in `tests/`.

## Next (ideas agreed or discussed — build only when the owner says so)
- **Etsy search** (Etsy Open API v3: listings → shops; keys already in Connections).
- **Amazon sellers** through search-engine results (limited).
- **Custom recipes**: per-site reading rules added as code (`app/methods.py` + a recipe module), chosen per directory.
- **Pictures** on cards: auto-grab a small logo / photo, change or re-grab it.
- **Watch lists** / alerts when a contact changes (new website, new products).
- **Test directory** for developers (a sandbox that never mixes with real data).
- Container logs inside the app (needs a safe way to read Docker logs).
- Etsy / Amazon “Sells on” detection for contacts found by web search.
- Learning: show “also fits <other directory>” suggestions; use embeddings by default when a model is installed.

## Later
- **Fine-tuning** a model on the exported decisions, on a GPU PC (RTX 4090 class); then use it as the Discover model.
- Bigger models on the GPU PC (Settings → AI servers → add server).
- Optional VPS hosting.
