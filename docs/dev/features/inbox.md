---
title: Inbox and decisions
order: 40
updated: v0.7
---
**What it does:** new companies wait for a person to **Accept** (into its directory or another) or **Reject** (with a reason). Tabs: New, Enriched, Rejected.

## How it works
- `inbox_routes`: items joined with contacts; people with “only own contacts” see only companies they found first.
- `contacts.accept()` adds a membership, sets `accepted_at`, logs a decision; `reject()` stores the reason; `restore()` brings it back.
- Once an item exists for (contact, directory) — waiting, accepted or rejected — later searches don't suggest it there again.
- Every decision goes to `decisions` (with a snapshot) for suggestions and training data.

## Files
`app/web/inbox_routes.py`, `templates/inbox.html`, `app/contacts.py`.

## Permissions
*Review the Inbox* to decide; *View* to look.
