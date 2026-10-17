---
title: Adding contacts by hand
order: 60
updated: v0.7
---
**What it does:** **+ Add Contact**: one contact, a pasted list, or a CSV file, with a duplicate check, then enrich now / tonight / not at all; optionally accept straight away.

## How it works
`add_routes`: rows → `contacts.upsert(added_by=…)` (the person becomes the first finder) → `to_inbox()` (method `manual` / `csv`). If the company already existed and was found by someone else, it is listed in their Existing Contacts.

## Files
`app/web/add_routes.py`, `templates/add_contact.html`, `_dupcheck.html`.
