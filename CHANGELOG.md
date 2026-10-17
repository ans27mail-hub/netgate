# What's new

## v0.7 — 17 Oct 2026 · Tags, card styles, themes, who sees what, backups

- **Tags** (Settings → Tags): coloured labels like *Customer* or *Sample sent*. They show as small bars on the card and can colour the whole card lightly. Filter and sort by tag, tag many contacts at once, or use **+ Tag** on a contact's big card.
- **Card styles A, B and C** and a **fixed card width** for each directory (Directory Settings → Cards), so cards don't squeeze when there are many. Display has “at most N per row”.
- **Short Card Shows…** on the big card: pick which fields the small card shows — for every card in the directory, or only for you.
- **Themes** (Settings → Themes): choose the look for everyone, let people pick their own, follow the computer's dark mode, or copy a theme and change its colours, font, corners and spacing. A **Dark** theme is included.
- **Bigger Help window** — the scrollbar is now inside, and Ask is always at the bottom.
- **Debug page** has the request buttons, **Back to Requests** and **Clear Debug Notes**.
- **What each person sees** (People → a user): all directories, chosen ones or only their own (directories now have an **Owner**); all contacts or only the ones they found first or added; and whether they may see the **search methods**.
- **Existing Contacts** tab in each directory: companies a person's search found that someone else had already found. The first finder stays. You choose per person whether they see the full card or only chosen fields, and whether they may enrich them.
- **Headings, menus and buttons** now use capital letters on each word (Title Case).
- **Developer Handbook** (Developer Tools): how NetGate is built, one page per feature, and pages made automatically from the code. Admins only, unless you give someone *Developer help*.
- **Automatic backups** every night (Settings → Backups), **Back Up Now** and download. Restoring is done on the server with `netgate restore`.
- **Running Jobs** on the Dashboard, beside Quick Actions.

## v0.6 — 16 Oct 2026 · Dashboard, Directories page, moving contacts, People

- **Dashboard** is the new start page (click **NetGate** or **Dashboard**): the numbers at a glance, what needs attention (with a button for each), quick actions, whether the AI server, browser, search engine and eBay are reachable, all directories, and recent activity.
- **Directories page:** every directory as a card with its contacts, Inbox waiting, % complete, search methods, keywords and last search, plus a **New directory** card. Grid or list, and sorting. The directories are no longer listed in the left menu.
- **Switch directories** with the tabs at the top of a directory's page, or **▾ Jump to…** when there are many.
- **Move contacts** to another directory: **Move here** / **Also add here** on a contact's card, or tick several in the list and use **Move there** / **Also add there**. Details and history are kept.
- **People** in the left menu, with Users, Roles & permissions and Login history:
  - users list with search, status and last login
  - new users choose their own password at first login
  - **reset password** (logs them out everywhere), switch off, **delete** (what they did is kept)
  - **login history**, including failed attempts
  - roles: new, **copy**, rename, **delete** (its users get the role you choose)
- **My password** under Settings, for everyone.

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
