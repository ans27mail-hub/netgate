---
title: Help Center
order: 110
updated: v1.0
---
**What it does:** user help: pages in `app/help/*.md` (front matter: title, section, order, needs, summary), the **?** button on every page (help window, scroll inside, Ask NetGate at the bottom), search, **Ask NetGate** (local AI answers only from the pages), What's New (`CHANGELOG.md`).

## Files
`app/help.py`, `app/web/help_routes.py`, `templates/help.html`, `_help_panel.html`.

Rule: every page has `help="<slug>"` and a help page; keep them in step with the code.

## v1.0
Help search weighs each query word by how rare it is across the pages (`log((N+1)/(1+df)) + 0.2`), so common words like “search” don't outrank the right page.
