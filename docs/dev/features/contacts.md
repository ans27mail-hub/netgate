---
title: Contacts, cards and the big card
order: 55
updated: v0.7
---
**What it does:** **All Contacts** (`/contacts`) and a directory page show contacts as short cards (grid) or a table (list). Clicking opens the **big card** with all details.

## How it works
- `_listing()` builds the query (visibility, filters incl. Tag, up to 500), completeness per contact, tags, sorting (incl. *Tag Order*), card settings.
- Visibility: `visible_records_clause()` / `own_clause()` in `common.py` (directories the person may see; only their own contacts when set).
- Big card: `_card()` → `_bigcard.html`: fields with their sources, Tags row (+ Tag menu), directories with Move Here / Also Add Here, Enrich Now, Edit, Short Card Shows…, Delete, history, “Found first by”.
- **Limited view** (v0.7): for a person who only sees their own contacts, someone else's contact (an Existing Contact) shows only what their setting allows (full card or chosen fields) and no edit / move / tag / delete.
- Edit (`/records/<id>/edit`) changes fields, name, description, notes; history records who.
- Export CSV, saved views, column choice per person.

## Files
`app/web/contacts_routes.py`, `templates/contacts.html`, `_bigcard.html`, `_table.html`, `_filters.html`, `app/web/filters.py`.
