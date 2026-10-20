# Decisions

A dated log of choices and why. Newest first within each date. Don't undo one without asking the owner.

## 2026-10-20 (v1.0)
- **Everything in one version:** the owner moved the Testing Guide and the Keyword Library into v1.0 and asked for directory cards to open on a click anywhere; testing and fixes follow in v1.1.
- **Keyword Library:** starter categories Products, Buyer types, Countries and cities, Extra words, plus “From directories” with every existing directory keyword (linked by `term_ids`). Combinations: one word from each ticked category, at most 100. Warnings: reject list, already a keyword (same language), searched in the last 14 days. Permission *Manage the keyword library* goes to every role that may manage directories; anyone who may run requests may open the library and the builder. Languages offered: German, Italian, French, Spanish, Dutch, Polish, Portuguese, Swedish, Danish, Czech, Greek, Turkish, Arabic, Urdu. *(Defaults chosen.)*
- **Browser search:** Bing and DuckDuckGo on by default, Google only when ticked. Defaults: 20 s pause between searches on one engine, 20 searches per hour per engine, wait 5 minutes for a person on a CAPTCHA, then rest the engine 6 hours. Directory defaults: 20 new companies, 5 result pages, 15 minutes. The renderer does one browser action at a time. The pop-up opens only for the person who started the request; others with *Control everyone's requests* use Solve on the Dashboard. *(Defaults chosen.)*
- **Verify** checks only values that came from a page (typed-in values show “Not from a page”), reads pages fresh (not from the cache), compares by code first (phones by digits, text without case; a value the page writes differently but code still finds counts as the same), and asks the AI only for one missing field. Nothing changes until a person clicks Accept New Value / Remove It / Keep Old. Night verify is off by default (0 months), max 30 contacts per night.
- **Profile & products:** the AI reads the home page and up to 3 product / about pages; categories are only from Settings → Product Categories (an MFI starting list for motorbike clothing, gloves and leather goods — editable); at most 30 products; pictures are only links (nothing downloaded). Making the profile again replaces NetGate's own products and keeps the ones people added. Products and Accept / Keep need *Edit contacts*; Verify and Profile follow the Enrich permission.
- **Testing Guide:** checklists are code (Markdown in `app/testguide/`), never edited in the web UI. Each step is tagged with the version that added it; tests require a checklist for every Handbook feature and at least one step for the current version. Permission *Testing Guide* (Developer tools group): Admins and the Developer role. Screenshots up to 5 MB, pictures only, stored in the database. A run can be deleted by its tester or an admin.
- **Test Directory** (`groups.is_test`): hidden from every directory list; its contacts are left out of All Contacts for everyone and its Inbox items for people without *Testing Guide*. Empty deletes only contacts that are in no other directory and not waiting in another Inbox.
- **Moving:** the field-adopt address is `/settings/directories/{id}/adopt-field` (a `/fields/adopt` address clashed with the field-edit route — found by the v1.0 test).
- **New library `beautifulsoup4`** (reads search-result pages in Browser search; `lxml` already came with trafilatura). The first `netgate update` to v1.0 rebuilds the app and the renderer, so it takes longer.
- **Help search** now weighs rare words higher than words on almost every page, so “how do I stop a search” finds *Requests* first again.

## 2026-10-20 (planning v1.1)
- **Testing Guide and Keyword Library go into v1.1**, after v1.0 (owner: “do it your way”).
- **Keyword translations:** keywords are kept in English; people tick the languages to search in; the local AI translates a keyword the first time it is needed and the translation is **saved** (marked AI-translated, editable, can be marked checked) and reused — not translated anew for every search, so results stay comparable and mistakes can be fixed once.

## 2026-10-20 (v0.9)
- **Interrupted, not failed:** a request cut off by a restart or 30 minutes without progress gets its own status *interrupted*, shown in the Failed tab with the same buttons. Workers start through `python -m app.worker` (docker-compose), which tidies their own queue first — there is one worker per queue, so whatever that queue was running can't be running any more. Waiting requests are queued again because Redis keeps no data across an update. *(Defaults chosen.)*
- **Force Stop** only for *Control everyone's requests*, only for Pausing / Stopping.
- **Pages read are kept for ever** (small rows; the base of Saved Pages). Discover skips a **list** page read for the **same directory** within 7 days (setting; 0 = off) — another directory reads it again; profiles aren't skipped on their own. Earlier tries of the same request are always skipped. Enrich skips pages read **for that company**, at any time, and reuses their code finds; *Check All Again* reads all. The site's home page is still fetched quietly to find its other pages. *(Defaults chosen.)*
- **Enrich search order:** name + place, the person's own words, website address, the search that found it, products, missing-field words, directory words, B2B sites, social; at most N searches (directory, default 8), N results each (default 8). *(Default chosen.)*
- **Enrich Now ▾** only for people with *See search methods*; others use the directory's steps. Greyed steps: eBay (no keys / no seller), Find own website (website known), Social (all three known). The last choice is remembered per person.
- **New permissions** *See the Dashboard*, *See the Inbox*, *See requests and AI jobs*: given by the upgrade to every role that could view contacts (so nobody loses anything). Without the Dashboard the start page is Directories. Keywords / last search / Existing Contacts are hidden from people with no search-related permission. **Cards Only** role = *View contacts* only (export off).
- **Look:** BrandPartners' presets became four built-in themes (with Archivo + Public Sans). Themes now have a text and a heading font. Uploaded fonts are stored in the database (`font_files`, max 3 MB) and served by NetGate. Personal look = theme + fonts + text size, only when *Let each person pick their own* is on. Button text colour follows the accent automatically (the old “white on accent” warning was dropped).
- **Pop-ups:** every `<details>` menu, the windows (click on the dark area) and the open card close on an outside click; Esc closes menus. Typed text in a window stays while the page is open.

## 2026-10-20 (planning v0.9)
- **v0.9 also gets** points 10 (stuck requests clean-up) and 11 (Enrich Now with a choice of steps) — owner said yes to both; and the owner's new asks 12 (permissions for every action, incl. a “cards only” level) and 13 (personal font and colour scheme in Display, like BrandPartners). Split by the owner: **v0.9 = 10, 5, 7 + 11, 12, 13, 14; v1.0 = 4, 8, 1.**
- **Point 13 follows BrandPartners' Appearance settings** (same GitHub account, `ans27mail-hub/brandpartner`): colour presets A–D, every colour editable, separate heading and body fonts from a bundled list, upload your own fonts. In NetGate it is also available per person in Display.
- **Point 14: every pop-up closes on a click outside it or Esc**, one menu open at a time (owner's request).
- **Solve CAPTCHA yourself** joins v0.9 point 4 (Browser search): a person may solve a CAPTCHA in a live pop-up of NetGate's browser, then the search continues. “Never solve CAPTCHAs” now means NetGate never solves them automatically (no AI, no solving service). Only for Browser search; SearXNG searches can't show their CAPTCHA. Limits per engine stay.

## 2026-10-18 (v0.8)
- **Delete only empty directories** is checked on the page and on the server. “Waiting” = Inbox items with status *new*; accepted / rejected Inbox items, existing hits, keywords and fields go with the directory; decisions and requests keep a cleared link (training data stays).
- **Fill the row is on by default** for everyone (also for saved v0.7 display settings, which had no such key). Directory setting: Default / On / Off.
- **Edit and Run Again changes the same request** (`jobs` row): the finished try goes into `params.tries`; counters show the current try; Inbox items of every try keep the request's id. Only Discover requests that are done / failed / stopped. The request stays its starter's (they stay the first finder); who edited is kept per try. A changed text or directory drops the keyword link (a keyword run becomes a normal request), so keyword counts stay right. *(Defaults chosen; owner didn't decide.)*
- **Go Deeper** = levels 1–3: per level two more search-result pages and one more “list” page, the page limit grows by `MAX_PAGES` per level, two more “next” pages per list; eBay looks at more listings / sellers. *(Default chosen.)*
- **Save as Keyword** needs *Run keywords* for that try's directory (or *Manage directories*), only for a try that found something; the keyword runs at night like the others. *(Default chosen.)*
- **Plain Run Again** now keeps the request's search methods (before, it dropped them by mistake).
- **Search engines are chosen per search** with SearXNG's `engines=` parameter, so no SearXNG config change and nothing to set up on the server; until the owner saves a choice, SearXNG's own defaults are used. The page needs *Crawler settings*. Every web search is logged (`search_log`, 30 days). “Blocking” = CAPTCHA / denied / too many / suspended / 403 / 429; other failures = “Not answering”. The Dashboard warns only about engines that are switched on.

## 2026-10-18 (planning v0.8)
- **Deleting a directory** needs it empty: no contacts and nothing waiting in its Inbox (the owner first chose to remove waiting Inbox items with it, then changed to blocking until they are accepted or rejected).
- **Everything stays in one app** — no separate Scanner (see v0.7 note).

## 2026-10-17 (v0.7)
- **Tags belong to all directories or chosen ones** (owner: OK). Shown as small bars under the Enrich button (owner chose this over circles at the top-left); one tag may tint the card (mixed into the theme's card colour so it works in Dark too). Anyone who may edit contacts can tag; *Manage tags* is needed to create / change / merge / delete tags.
- **Card style and width are per directory** (Directory Settings → Cards), default from Display. “Short card shows” can be saved for every card in the directory or only for me.
- **Themes only change colours, font, corners and spacing**, never the layout. Built-in themes can't be edited, only copied. Theme for everyone + optional personal choice + optional “Dark when the computer is in dark mode”.
- **Own contacts = found first or added by that person** (`records.found_by`). The first finder is kept; no “found again” history on the contact (owner). A later search by someone else lists it in their **Existing Contacts** tab (`existing_hits`), with full card or chosen fields per person, and *Enrich other people's contacts* as a permission.
- **Directories get an Owner**; “only their own directories” means owned or created by them. Existing directories got the first admin as owner.
- **Search methods are hidden** unless the person has *See search methods* (Admin, Manager, Developer by default; not Researcher / Viewer). Without it, their searches use the directory's methods.
- **Title Case** for headings, menus, tabs and buttons; normal sentences stay normal.
- **Developer Handbook**: admin-only by default, grantable with *Developer help*. Written pages in `docs/dev/` (one per feature, test enforced) + automatic pages from the code. Never contains passwords or keys.
- **Backups** run in their own small container (`backup`, postgres:16-alpine) with `pg_dump`, into `BACKUP_DIR` (default `./backups`; better on another disk). The web app only reads the folder. **Restore only on the server** (`netgate restore`, which first saves a safety copy), never from the web page.
- ~~NetGate Scanner as a separate app~~ — **changed 18 Oct 2026 by the owner: everything stays inside NetGate** (separate apps would be more complicated). Page saving and scans become part of NetGate, with their own worker container in the same stack; the Chrome extension connects to NetGate.

## 2026-10-16 (v0.6)
- **Start page = Dashboard** (was the Inbox). `/?group=` still redirects to the directory (v0.4 links).
- **Directories leave the sidebar**; they live on the Directories page (cards / list). Inside a directory: **tabs + “Jump to…”** (owner chose both).
- Dashboard and Directories card contents **as drawn in the D5 mockups** (owner: “keep as it is for now”). “% complete” on cards = share of the directory's fields that are filled, over all its contacts.
- **Moving only moves** (owner): no “enrich now” option in the move box. Enrich works as before. The box says which new fields will show as Missing. A move needs *Edit contacts* for both directories and is logged as a decision `move` (not used for AI suggestions).
- **Deleting a user keeps everything they did**; the name shows as “(deleted user)”. Their requests stay without an owner. You can't delete or disable yourself; the last active admin can't lose the Admin role.
- **Password reset** by an admin logs the person out everywhere and (by default) makes them choose their own password at the next login. New users get “must choose own password” by default.
- **Login history** keeps every attempt (also failed, with the reason) for 180 days; not tied to the user row so it survives deletion.
- **Deleting a role** asks which role its users get instead; the Admin role can't be deleted. Copying a role copies its permissions and default directory access.
- **Planning decisions (not built yet):** see `docs/ROADMAP.md` → *Next — agreed plan* (Saved Pages & Scans inside NetGate — not a separate app, extension talks to NetGate, Authentik + per-app Login method switch, Vaultwarden, screenshots manual only, page-keeping rules editable, Verify single + automatic, product images cached on view and deleted after X days).

## 2026-10-16 (v0.5)
- **Requests are a separate layer.** Deleting or rejecting a request never changes contacts, their data, sources or Inbox items. Each contact keeps a plain-text history note (“Found by Web search ‘glove makers’ · 16 Oct 2026 · admin”), so it still makes sense after the request is gone. The database link from a contact to its request is cleared, never cascaded. *(Owner's request.)*
- **Deleted requests** go to a Deleted tab for 30 days (restorable), then the scheduler removes them. There is no “also delete contacts” option. Contacts are only removed on purpose (Inbox, or a contact's card).
- **Reject a request** = stop it (if running) + put its keyword on the reject list with a reason. Contacts it found are not rejected; they wait in the Inbox as usual.
- **Reject list matching:** exact keyword after normalising (lower case, word order, plurals, small words like “the / top / list” ignored). Similar keywords (Jaccard ≥ 0.5) only get a warning. *(Default chosen; owner didn't decide.)*
- **Inbox before directory:** nothing found by a search reaches a directory until a person accepts it. Hand-added contacts also go to the Inbox, unless a person who may review ticks “accept straight away”.
- **One contact, many directories:** a contact exists once (`records`) and belongs to directories through `memberships`. Inbox items are per (contact, directory). Once a contact has an Inbox item for a directory (waiting, accepted or rejected), later searches don't suggest it again for that directory — rejected stays rejected.
- **Matching the same company:** marketplace id (e.g. eBay seller name) → website domain → name (+ city). Across all directories.
- **Groups became directories** (the code and tables still say `group`). v0.4 listings became accepted members of their group; nothing was lost. Keywords stay with their directory and are shown in the Inbox.
- **Suggestions, not decisions:** “AI suggests …%” is a nearest-neighbour vote over past accept / reject decisions for the same directory (word-hash vectors by default, Ollama embeddings optional). It never decides on its own. Real fine-tuning is later, from the exported decisions.
- **Roles:** Admin (locked, everything), Manager, Researcher, Viewer, Developer. Changing a role changes everyone with it. **Per-person exceptions allowed**, shown with a “custom” badge. **Directory access is per person**, with a default from the role. *(Defaults chosen; owner didn't decide.)* Existing users got the closest role, with exceptions so they keep exactly their v0.4 access. The old `users.perms` column is still written (v0.4 names) so a rollback keeps working.
- **Developer role** = tools inside the app (debug trace, app log, page tester, training export, developer help). Code changes only through GitHub. No access to users or API keys by default.
- **Container logs** are not read from the web app (that would need the Docker socket, a security risk). NetGate writes its own log table; container logs stay in WSL (`docker compose logs`).
- **eBay search uses the official Browse API** (client-credentials token). Business sellers only by default; where eBay rejects the business filter (e.g. some marketplaces) the search is retried without it and each seller's account type is checked. Seller page link: `https://www.<site>/usr/<seller>`.
- **Etsy, Amazon and Custom recipes** are shown as “later” in the method list, not built yet.
- **Help lives in the repository** (`app/help/*.md`) and ships with each version; it is not editable in the UI. Pages can be limited to people with certain permissions (`needs:`).
- **Handover files** (`AGENTS.md`, `docs/`) are updated every work session. `CLAUDE.md` only points to `AGENTS.md`.
- Database upgrades take a Postgres advisory lock, because the web app and the scheduler both start them.

## 2026-10-16 (v0.4)
- The headless browser runs in its own container (`renderer`, Playwright Chromium on Debian 12 “bookworm” — Playwright 1.48 can't install its dependencies on Debian 13 “trixie”). It runs 24/7 for night jobs, is separate from the owner's own Chrome, memory-capped, and updates with the app. Used only when a page needs it (“auto”).
- Polite crawling: robots.txt, 2 s per-site delay, one retry. Cache 3 days.
- Code-first extraction; the AI is only asked for what code couldn't find.
- API secrets are never displayed; empty input keeps the saved value, “-” removes it.
- eBay default marketplaces: UK, DE, IT, FR, USA, Canada.

## 2026-10-15 (v0.1–v0.3)
- Stack: Python FastAPI + Jinja2 + HTMX, PostgreSQL, Redis + RQ workers, SearXNG, Ollama on the iMac. Docker in WSL on the owner's PC.
- Updates through GitHub: `netgate update` / `rollback` read `releases.txt` (git tags can't be pushed from the AI's environment).
- Version numbers are v0.x.
- Layout direction “D” (dark top, cards), later D4 (left sidebar) — see `docs/DESIGN.md`.
- Scripts / methods are never editable in the web UI.
- Night jobs run in a time window and stop by themselves; a separate night worker so daytime jobs don't wait.
- OpenRouter optional, with spending limits and a fallback to Ollama.
