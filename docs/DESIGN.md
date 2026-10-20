# Design

## Direction
- **v0.2–v0.4:** layout “D” — dark top bar, directory tabs, compact cards that open into a big card, optional list view.
- **v0.6:** layout **D5** — sidebar: Dashboard, Inbox, All contacts, Directories, Saved views; bottom: Requests, People, Settings, Help, Developer tools. Directory pages get a tab bar (switcher). Mockups D5-Dashboard, D5-Directories, D5-Directory, D5-Move on the design canvas.
- **v0.5:** layout **D4** — a dark **left sidebar** (Inbox with count, All contacts, Directories with counts and a find box, Saved views; at the bottom Requests, Settings, Help, Developer tools, user) and a white top bar (search, AI jobs running, ?, + Add contact, + Run discovery).

The D4 mockups are on the owner's design canvas (claude.ai artifact *NetGate layouts*): artboards D4-Inbox, D4-Contacts, D4-Directory, D4-NewDirectory, D4-AddContact. Screenshots of the built pages are in `docs/design/`.

## Look
- Font: Instrument Sans (UI), JetBrains Mono (addresses, codes).
- Colours: ink `#16181d`, page `#f4f6f9`, cards white with `#e3e6eb` border, accent blue `#2457d6`. Method badges: eBay amber, Etsy rust, web blue, directory green, manual purple.
- Filter chips are black with a ×; “+ Add filter” is a dashed chip.
- Completeness bar: green ≥ 80 %, blue, amber < 50 %.
- Plain-English labels, short hints under fields, no jargon.

## v0.7 additions
- Card styles **A** (tag bars right, under the Enrich button), **B** (left), **C** (one line with the name); fixed card width per directory. Tag colours: 10 fixed colours; a tag may tint the card (mixed into the theme's card colour).
- Themes are CSS variables on `:root` (`app/themes.py`); every colour in `app.css` uses them, so new CSS must use `var(--card)`, `var(--ink)` etc., never fixed white.

| Page | Screenshot |
|---|---|
| Big card with tags | `design/v07-big-card-tags.png` |
| Settings → Tags | `design/v07-tags.png` |
| Settings → Themes | `design/v07-themes.png` |
| Dark theme | `design/v07-dark.png` |
| Settings → Backups | `design/v07-backups.png` |
| Developer Handbook | `design/v07-handbook.png` |
| A user: What This Person Sees | `design/v07-user-sees.png` |
| Help window | `design/v07-help-window.png` |

## v1.0 additions
- **Dashboard:** tiles `auto-fit` over the full width; Needs Attention and Running Jobs share the middle evenly (`flex: 1 1 340px`).
- **Click anywhere:** directory cards and list rows have `data-href`; one handler in `base.html` opens them unless a button, link, form field or selected text was clicked.
- **Keyword Library:** categories on the left, words as a table with ticks for bulk actions; language chips (DE, IT …) — filled = checked, outlined = AI. **Search Builder:** words as toggle chips per category, languages as checkboxes, a table of searches with warning badges.
- **Solve CAPTCHA:** a large dialog with the live picture (refreshed about twice a second), a text box, Enter / Tab, Give Up; Later closes it for this page.
- **Company page:** header with Verify and Profile buttons, a Details table (amber rows wait for a decision), Profile as chips, Products as a picture grid.
- **Testing Guide:** three panels (start a run, health check, Test Directory); each step is a bordered row with a coloured left edge (green passed, red failed, grey skipped), round result chips, a note box and a Screenshot button.

| Page | Screenshot |
|---|---|
| Dashboard (full width tiles) | `design/v10-dashboard.png` |
| Directories | `design/v10-directories.png` |
| Keyword Library / a word / Search Builder | `design/v10-keywords.png`, `design/v10-keyword-edit.png`, `design/v10-builder.png` |
| Solve CAPTCHA pop-up / on the Dashboard | `design/v10-captcha-popup.png`, `design/v10-attention-captcha.png` |
| Browser Search settings | `design/v10-browser-settings.png` |
| Company page (phone: `v10-phone-company.png`) | `design/v10-company.png` |
| Product Categories | `design/v10-product-categories.png` |
| Move preview on the big card | `design/v10-bigcard-move.png` |
| Directory Settings (languages, Same as) | `design/v10-dir-settings.png` |
| Testing Guide / a run / health check | `design/v10-testing.png`, `design/v10-test-run.png` (phone: `v10-phone-test-run.png`), `design/v10-health.png` |

## v0.9 additions
- **Enrich Now ▾**: a split button; the menu lists the steps with a grey reason when one can't work. On phones it opens as a sheet at the bottom of the screen.
- **My Look** (Display): colour sets as cards with three swatches (menu, accent, page) and the fonts; a font sample line.
- Colour sets A–D come from BrandPartners; headings may use their own font (`--display`); button text follows the accent (`--accent-fg`).
- Pop-ups close on an outside click or Esc.

| Page | Screenshot |
|---|---|
| Enrich Now ▾ | `design/v09-enrich-menu.png` (phone: `design/v09-phone-enrich.png`) |
| Pages Read on the open card | `design/v09-bigcard-pages.png` |
| Directory Settings → Enrich | `design/v09-dir-enrich.png` |
| Interrupted requests | `design/v09-interrupted.png` |
| Settings → Themes (colour sets, Fonts) | `design/v09-themes.png` |
| My Look / with a personal look | `design/v09-my-look.png`, `design/v09-my-look-cards.png` |
| Cards Only | `design/v09-cards-only.png` |

## v0.8 additions
- Contact cards: **Fill the row** — width is a minimum, cards stretch evenly (like the directory cards).
- Search Engines: switches per engine, status badges (Working green, Blocking red, Not Answering amber), links per engine as chips.

| Page | Screenshot |
|---|---|
| Settings → Search Engines | `design/v08-search-engines.png` (phone: `design/v08-phone-engines.png`) |
| Edit and Run Again | `design/v08-edit-run-again.png` |
| Cards filling the row | `design/v08-cards-fill.png` |
| Delete Directory, blocked | `design/v08-delete-blocked.png` |
| Dashboard with an engine warning | `design/v08-dashboard.png` |
| Debug: engine of each link | `design/v08-debug-engines.png` |

## Pages (v0.6 screenshots)
| Page | Screenshot |
|---|---|
| Dashboard | `design/dashboard.png` |
| Directories | `design/directories.png` |
| A directory with the switcher | `design/directory-switcher.png` |
| Users (People) | `design/people-users.png` |

## Pages (v0.5)
| Page | Screenshot |
|---|---|
| Inbox | `design/inbox.png` |
| All contacts (list) | `design/contacts.png` |
| A directory | `design/directory.png` |
| Add contact | `design/add-contact.png` |
| Requests | `design/requests.png` |
| New directory | `design/new-directory.png` |
| Roles & permissions | `design/roles.png` |
| Help | `design/help.png` |
| Inbox on a phone | `design/mobile-inbox.png` |

## Owner's preferences
- Show mockups before building bigger layout changes.
- Display width setting: fixed px, % of the screen (adjustable), or full width.
- Cards: picture top-left (planned), hover popup with the description, click to open the big card.
