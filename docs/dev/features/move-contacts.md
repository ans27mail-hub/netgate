---
title: Moving contacts between directories
order: 65
updated: v0.7
---
**What it does:** **Move Here** / **Also Add Here** on the big card; **Move There** (with a confirm box) / **Also Add There** in the list view.

## How it works
`contacts.move(rec, from_ids, to_id, user)`: adds the membership in the target, closes a waiting Inbox item there, removes the source memberships, writes history (“Moved from A to B by …”) and a `move` decision. Details are never changed. The confirm box says which new fields will show as Missing (`_extra_note`). Needs *Edit contacts* in both directories. Limited (Existing) contacts can't be moved.

## Files
`app/contacts.py → move`, `app/web/contacts_routes.py` (`record_directory`, `move_selected`).
