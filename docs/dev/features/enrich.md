---
title: Enrich (filling missing details)
order: 50
updated: v0.9
---
**What it does:** fills a contact's empty fields.

## How it works
`jobs.enrich(record_id, steps)` uses the fields of all directories the contact is in (or waiting for), then steps from `methods.ENRICH_STEPS`: eBay store lookup → find own website → company website (home, Contact / About / Impressum, sitemap; code first, then AI with `ENRICH_PROMPT` on missing fields only) → social links → other pages and search snippets. Only empty fields are filled; the source page is stored per field.

## Who may enrich
`contacts.may_enrich()`: the *Enrich* permission, and for contacts someone else found first also *Enrich other people's contacts* (v0.7).

## v0.9 — stronger searching, steps, pages read
- `enrich(ctx, record_id, refresh, steps, words)`. Steps: the request's (`jobs.params.steps`, from **Enrich Now ▾**) or the directory's (`groups.enrich.steps`, Directory Settings → Enrich), else all. `refresh` = *Check All Again*; `words` = extra search words.
- `jobs.enrich_config(group)`: `{"words", "steps", "results" (per search, 1–30, default 8), "searches" (per contact, 1–30, default 8)}`.
- Searches, in order, deduplicated, cut at `searches`: name + place; the person's words; `"domain"` of the website; name + the keyword that found it (`inbox.keyword`); name + products; name + city + missing field words; name + directory Enrich words; name `site:` the directory's B2B sites (Directory site search option); social `site:` searches. Each trace has `why`. Stops when nothing is missing (and no social link is wanted).
- **Pages read**: `pages.read_for_record()` → `open_page()` skips URLs read before for this company (trace note) and merges the stored code finds (`pages_read.found.code`) with `merge_info()`; the home page of an already-read site is fetched quietly (cache) only to find its other pages. `refresh` reads all again.
- `fill` traces: field, value, source page; `pages.add_found(row, filled=[…])`.
- Routes: `contacts_routes.enrich_step_choices()` (greyed reasons), `enrich_choice()` (remembered in `users.prefs.enrich_choice`), `_choice_from_form()` — only for people with *See search methods*; others get the directory's steps. Template `_enrich_menu.html` (big card and Enrich Selected with `form="sel"`).

## Started from
Card button, big card **Enrich Now**, list **Enrich Selected**, Inbox **Enrich**, **Enrich All Incomplete** (50 least complete), Dashboard *Enrich Them*, night run.

## Files
`app/jobs.py → enrich`, `app/crawl.py`, `app/extract.py`.
