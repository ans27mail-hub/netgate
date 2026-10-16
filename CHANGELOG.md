# What's new

## v0.5 — 16 Oct 2026 · Discovery Inbox, directories, roles, help

- **New layout** with a menu on the left: Inbox, All contacts, your directories, saved views, Requests, Settings, Help.
- **Discovery Inbox.** New companies wait here until someone accepts them. Tabs New / Enriched / Rejected; reject with a reason; restore from the Rejected tab. A rejected company isn't suggested again for the same directory.
- **AI suggestions** in the Inbox (“Online retailers 94% · like 23 you accepted”), learned from your accept / reject decisions. Decisions can be downloaded as training data.
- **One contact, several directories.** Groups are now directories; a contact can be in more than one. Existing listings stay where they were.
- **All contacts** with filter chips (directory, country, city, has email / phone / website, completeness, date, keyword, method, any directory field) and **saved views**.
- **Search methods per directory:** Web search, Directory site search, **eBay search** (official API: sellers, ratings, business name, address, email, phone), Company website. Etsy, Amazon and custom recipes are shown for later.
- **Fields know where they come from** (“Filled from”: AI + code, company website, manual only, or an eBay value).
- **New directory** in five steps: basics, methods, fields, instructions, keywords.
- **Add contacts by hand:** one contact, a pasted list or a CSV file, with a duplicate check; then enrich with the steps you choose, now or tonight.
- **Edit a contact** by hand; notes are given to the AI.
- **Request controls:** Pause, Resume (continues where it stopped), Stop, Delete (Deleted bin for 30 days), Reject (keyword goes on the reject list), Run again, bulk actions and Pause all. Tabs All · Running · Waiting · Paused · Done · Failed · Stopped · Rejected · Deleted. Deleting or rejecting a request never changes contacts.
- **Reject list** for keywords (ignores capitals, word order and plurals; similar keywords get a warning).
- **Roles & permissions:** Admin, Manager, Researcher, Viewer, Developer, editable in a grid; per-person exceptions with a “custom” badge; directory access per person with a role default. Existing users were given the closest role and keep exactly the access they had.
- **Developer tools:** debug view per request (pages read, what code found, AI questions and answers), NetGate's own log, page tester, training-data export.
- **Help Center** with a **?** on every page, “Ask NetGate” (answers from the help pages with your own AI) and this What's new page.
- Handover files in the repository (AGENTS.md, docs/) so any AI assistant or developer can continue the project.

## v0.4 — 16 Oct 2026 · Crawler upgrade

- Headless browser (Chromium) for pages that need JavaScript.
- Follows next pages of lists; opens directory profile pages.
- Code-first details: emails (also hidden), phones, WhatsApp, social links, schema.org company data.
- Reads Contact / About / Impressum pages and the sitemap; splits long pages.
- Page cache; polite limits (robots.txt, per-site delay, one retry).
- Settings → Crawler and Settings → Connections (eBay / Etsy keys).

## v0.3 — 15 Oct 2026 · Discover + Enrich

- Discover finds companies; Enrich fills missing fields; night jobs.
- AI servers: Ollama, a GPU PC later, optional OpenRouter with spending limits.
- Compact cards with an open card, list view with columns, display width.

## v0.2 — 15 Oct 2026 · Login and groups

- Login, users and permissions; groups with keywords and fields.

## v0.1 — 15 Oct 2026 · Starter

- Search, crawl and save with the local AI.
