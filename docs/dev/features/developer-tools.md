---
title: Developer Tools and this Handbook
order: 115
updated: v0.7
---
**What it does:** Developer Tools (`/dev`): debug traces on / off, NetGate's log, page tester, training-data export, and this **Handbook** (`/dev/handbook`, permission *Developer help*, Admin and Developer by default).

## How the Handbook stays current
- Written pages: `docs/dev/*.md` (guides) and `docs/dev/features/*.md` (one per feature in `app/handbook.py → FEATURES`). Each has `updated: v0.x`.
- Automatic pages, made from the code when opened: addresses (routes), database tables, permissions, settings and defaults, AI prompts, versions and containers.
- `tests/test_v07.py` fails when a feature in `FEATURES` has no page. When you add a feature: add it to `FEATURES`, write its page, update `updated:`.
- **Ask the Handbook** uses the local AI with the best-matching pages.
- The Handbook never contains passwords or keys.

## Files
`app/handbook.py`, `app/web/help_routes.py`, `templates/handbook.html`, `dev.html`.
