---
title: What each person sees (own contacts, directories, methods)
order: 95
updated: v0.7
---
**What it does:** per person (default from the role):
- **Directories:** All · Only selected · Only their own (`users.dir_scope`; own = `groups.owner_id`).
- **Contacts:** All · Only their own (`users.contacts_scope`; own = `records.found_by` = they found it first or added it).
- **Existing contacts** their searches find: full card or chosen fields (`existing_view`, `existing_fields`).
- Permissions **See search methods** and **Enrich other people's contacts**.

## How it works
- `User.group_ids` = selected directories + owned ones; `auth.can()` uses it for directory permissions.
- `auth.own_contacts_only(user)`; clauses in `common.py` (`visible_records_clause`, `own_clause`, `inbox_clause`), directory counts in `dir_stats(user)`, Inbox filter, Dashboard activity.
- First finder: `jobs.save_found()` passes the request's user to `contacts.upsert(found_by=…)`; hand-added → `added_by`. The upgrade sets it for old contacts from `added_by` or the request's user.
- **Existing Contacts:** when a search (or a hand add) hits a contact someone else found first, `contacts.note_existing_hit()` stores one row per person + contact + directory (`existing_hits`). The directory tab lists them (own-scope people: their own; reviewers: everyone's), with first finder and who found it again. The contact keeps its first finder; there is no “found again” history on the contact.
- `contacts.can_see_record()` lets an own-scope person open an Existing Contact in **limited view**; `may_enrich()` needs *Enrich other people's contacts* for non-own contacts.

## Files
`app/auth.py`, `app/contacts.py`, `app/web/common.py`, `app/web/contacts_routes.py`, `app/web/people_routes.py`.
