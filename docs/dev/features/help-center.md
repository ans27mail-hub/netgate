---
title: Help Center
order: 110
updated: v0.7
---
**What it does:** user help: pages in `app/help/*.md` (front matter: title, section, order, needs, summary), the **?** button on every page (help window, scroll inside, Ask NetGate at the bottom), search, **Ask NetGate** (local AI answers only from the pages), What's New (`CHANGELOG.md`).

## Files
`app/help.py`, `app/web/help_routes.py`, `templates/help.html`, `_help_panel.html`.

Rule: every page has `help="<slug>"` and a help page; keep them in step with the code.
