---
title: Moving contacts between directories
order: 65
updated: v1.0
---
**What it does:** **Move Here** / **Also Add Here** on the big card; **Move There** (with a confirm box) / **Also Add There** in the list view.

## How it works
`contacts.move(rec, from_ids, to_id, user)`: adds the membership in the target, closes a waiting Inbox item there, removes the source memberships, writes history (“Moved from A to B by …”) and a `move` decision. Details are never changed. The confirm box says which new fields will show as Missing (`_extra_note`). Needs *Edit contacts* in both directories. Limited (Existing) contacts can't be moved.

## Files
`app/contacts.py → move`, `app/web/contacts_routes.py` (`record_directory`, `move_selected`).

## v1.0
- Move preview: `contacts_routes.move_preview()` → `_movepreview.html` (kept but hidden / missing / `enrich_now`), loaded with HTMX on the big card and in the list Move dialog; `enrich_now` starts `enrich_many` for the moved contacts.
- Other Details on the big card (`_card` → `other_details`) with **Add This Field** → `POST /settings/directories/{id}/adopt-field` (same data key, the other field's name and type).
- **Same as**: `POST /settings/directories/{id}/fields/{fid}/same-as` — the field takes the other key (values copied first), `groups.links[fid] = {own, same_as}`; empty = back to its own key.
