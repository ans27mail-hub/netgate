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

### v0.6 — Dashboard, Directories page, moving contacts, People (16 Oct 2026)
- **Dashboard** is the start page (logo and menu item): at-a-glance numbers, Needs attention (with action buttons), Quick actions, System status (AI server, renderer, search engine, eBay), Directories table, Recent activity.
- **Directories page**: one card per directory (contacts, Inbox waiting, % complete, methods, keywords, last search, run all keywords, Settings) + a “New directory” card; grid / list (remembered), sort. Directories are no longer listed in the sidebar.
- **Directory switcher** on a directory's page: tabs for every directory + “▾ Jump to…” with a search box + “← All directories”.
- **Move contacts**: on the card “Move here” / “Also add here” (with *from* when in several directories); in list view “Move there” (confirm box) / “Also add there”; on All contacts *From: all their directories or one*. Only moves; enrich as usual.
- **People** in the sidebar (tabs Users · Roles & permissions · Login history): users list with search / role / status / last login; add with “must choose own password”; reset password (logs out everywhere); disable; delete (data kept, “(deleted user)”); login history incl. failed attempts (180 days); roles: new / copy / rename / delete with “give its users this role”. Everyone: Settings → My password.

### v0.7 — tags, card styles, themes, who sees what, Existing Contacts, Handbook, backups (17 Oct 2026)
- **Tags**: Settings → Tags (colour from 10, order, “colour the card”, all directories or chosen ones, merge, delete); small tag bars under the Enrich button and a light card tint; tag bar with counts, Tag filter, sort by tag order, bulk Add / Remove tag; + Tag on the big card.
- **Card style A / B / C and fixed card width** per directory (Directory Settings → Cards) and in Display; Display “at most N per row”, so cards no longer squeeze.
- **Short Card Shows…** on the big card: choose up to 3 fields, for every card in the directory or only for me.
- **Themes** (Settings → Themes): theme for everyone, personal themes, follow dark mode, copy / edit with 8 colours, font (incl. Noto Sans), corners, spacing; built-in NetGate Classic and Dark.
- **Bigger Help window** with fixed header, inner scrolling and Ask at the bottom.
- **Debug page**: request actions, Back to Requests, Clear Debug Notes.
- **What each person sees**: directories all / selected / own (directories have an Owner); contacts all / own (own = found first or added); permission **See search methods**.
- **Existing Contacts** tab: contacts a person's search found that someone else found first (first finder kept). Per person: full card or chosen fields; permission **Enrich other people's contacts**.
- **Title Case** for headings, menus, tabs and buttons.
- **Developer Handbook** (Developer Tools → Handbook, permission Developer help): written guides + one page per feature (`docs/dev/`), automatic pages from the code (addresses, tables, permissions, settings, AI prompts, versions), search and Ask; a test fails when a feature has no page.
- **Automatic backups**: own `backup` container, every night (time and days kept in Settings → Backups), Back Up Now, download; `netgate backup` / `netgate restore` on the server only.
- **Running Jobs** panel on the Dashboard beside Quick Actions.

## Next update list (v0.8, agreed 17 Oct 2026 — build only when the owner says “build v0.8”)
1. **Verify + Company page** (see item 1 below: where each value came from, re-check, short profile, products).
2. **Delete a directory only when it has no contacts.** Delete is switched off with “still has N contacts — move or remove them first” and a link to the list. Companies still waiting in the Inbox for it are removed with it, after a warning in the confirm box (owner chose B).
3. *(waiting for the owner's OK)* **Settings → Search Engines**: turn SearXNG engines on / off, see which work or block, results per engine; optional official search keys as backup (Brave, Google, Serper …; check prices first); Debug shows which engine gave each link.
4. **Browser search** method: the renderer's Chromium opens Bing / DuckDuckGo (Google only if switched on), reads result pages and listing pages, keeps going until the directory's need is met. Stop rule per directory: N new matching companies, max result pages, max time. Pause between searches, max searches per hour; on a CAPTCHA the engine pauses for hours and the Dashboard says so (never solve CAPTCHAs).
5. **Permanent list of pages read** (link, when, which request, what was found, which company). Enrich reuses what was found and only opens unread pages; discovery skips listing pages read recently unless “read again after N days”; Verify re-reads on purpose; Debug / Company page show the pages. Becomes the base of the Saved Pages part of NetGate.
6. **Edit and Run Again inside the same request** (finished / failed / stopped only): change search text, directory, methods (if allowed), “Go deeper” (more result pages). The request keeps a history of tries (text + found). Pages read in earlier tries are skipped (uses 5). 0 results → hint “Nothing found — try different words or Go deeper”. **Save as Keyword** from a good try. Plain Run Again stays. Own requests with *Control own requests*, others with *Control everyone's*. Nothing found earlier is removed.
7. **Stronger Enrich searching.** Smarter searches from what is known (the keyword / request that found it, its products, its website address in quotes, the directory's B2B sites with `site:`); **own Enrich search words** per directory (Directory Settings → Enrich) and a box for words for one contact on **Enrich Now**; choose the Enrich steps per directory; depth settings (results read per search, max searches per contact); stop early when all fields are filled; skip pages already read (uses 5); Debug shows each Enrich search and which result filled which field.
8. **Moving between directories with different fields.** Preview when moving (“kept but hidden: …”, “missing in the new directory: …” + tick “Enrich the missing fields now”); **Other Details** section on the big card for details kept from other directories, with “Add this field to this directory”; **Same as…** in Directory Settings → Fields to link differently named fields (e.g. Materials = Products) so they share the data.
- Not chosen: “Items, not companies” directories (owner uses a supplier directory with a Materials field instead).

## Next — agreed plan (build each only when the owner says “build”)
Agreed order (16 Oct 2026):
1. **NetGate v0.8 — where each value came from + Verify.** Every value stores page link, saved-page id (Saved Pages, later), method (auto scan, manual capture, eBay API, by hand, CSV), found date, last checked. **Verify** button on the full card (re-checks those pages, shows same / changed with Accept / Keep old, page gone) + a night setting “re-check contacts not verified for N months”. **Short company profile** (type, product categories, main products, materials, markets, certifications) and a **Company page** (all fields with sources and verify dates, products, saved pages, history, notes, directories). **Products** as their own records (name, category, image link, source page, price / MOQ). One shared **MFI product category list** (draft it when the owner asks).
2. **Saved Pages & Scans inside NetGate** (owner, 18 Oct 2026: *not* a separate app — one app, one login, one database, one `netgate update`). Heavy scans run in their own worker container in the same Docker stack so the web pages stay fast; saved pages are stored in a folder set in `.env` (like backups). Saves pages (manual and auto whole-site scans) and manages them: Sites (value score), Pages, Versions, Finds, Scans, Captures, Recipes; pages Sites/Library, one site, New scan, Scans, Captures, Search, Recipes, Storage (in NetGate's own menu and Settings). Page-keeping rules with defaults, editable in Settings + per-site override. Screenshots off unless turned on per site / scan. A “Saved pages” search method, scan jobs as normal requests, saved pages shown on the Company page; the crawler, renderer and pages-read list are shared.
3. **Chrome extension** — connects to NetGate (key from Settings → Connections): Save page, auto-capture switch; settings: key, auto-capture sites, never-capture list, help with scans. Helps the server, doesn't replace it.
4. **Sources list + products + image cache** (needs Saved Pages). Every website used, with a type (e-commerce portal, marketplace, B2B directory, company website, forum, trade show, news, social), value, last used, login needed (→ Vaultwarden folder), blocks robots, contact, notes. Product images: only links in the database; fetched when a Company page is viewed, shrunk, deleted after X days unviewed (X in Settings), “Keep images” per company, optional night pre-fetch for accepted companies. When a site blocks image downloads: direct with the page as referrer → open the page in Chromium and catch the images → screenshot of the product area → Chrome extension while the person views the page. Internal use only.
5. **User Wallet** (one login for all factory apps) with **Authentik**; each app has a setting *Login method: Site login / Authentik / Both* (no code change to switch), admin accounts always stay in the app, plus an emergency command back to site login. The Wallet gives app access and role (Authentik groups); each app keeps its own permission grid. **Vaultwarden** for passwords of outside websites (owner will use it). Separate from NetGate, set up any time.

## Other ideas (not scheduled)
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
