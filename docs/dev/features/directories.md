---
title: Directories and the directory page
order: 20
updated: v1.0
---
**What it does:** a directory (table `groups`) is a list like *Manufacturers*. The **Directories** page shows them as cards or a list; each opens `/d/<id>` with its contacts, a tab bar to switch directories, and the **Existing Contacts** tab.

## How it works
- `dashboard_routes.dir_stats()` gives per directory: contacts, waiting in Inbox, % of fields filled, keywords, never-run keywords, last search, top missing field — counted over the person's own contacts when they only see their own.
- Directory page = `contacts_routes.directory_page()` → `_listing()` (filters, tags, sorting, completeness stats, card settings).
- Switcher: `_dirswitch.html` (tabs + “Jump to…” with a search box), counts from memberships.
- Directory Settings (`settings_routes`): Basics & Methods (incl. **Owner**), **Cards**, Fields, Instructions, Keywords, Test a Page, Delete. Creating a directory makes the creator its owner.
- **Delete only when empty** (v0.8): `settings_routes.delete_blockers()` counts memberships and Inbox items with status *new* for the directory; the Delete button is disabled with links to `/d/<id>?view=list` and `/inbox?dir=<id>`, and `directory_delete()` refuses on the server too. Accepted / rejected Inbox items and existing hits go with the directory (FK cascade); decisions and requests keep a cleared link.

## Data
`groups` (methods JSON, instructions, `owner_id`, `card`), `fields`, `keywords`, `memberships`.

## Settings & permissions
*Manage directories* to create / change; *View contacts* (per directory) to open.

## Tests
`test_v06.py`, `test_v07.py`, `test_v08.py` (delete only when empty).

## v1.0
Cards and list rows carry `data-href`; the click handler in `base.html` opens them unless the click was on a link, button, form field, label, summary or selected text. The Test Directory (`groups.is_test`) is left out by `common.all_groups()`.
