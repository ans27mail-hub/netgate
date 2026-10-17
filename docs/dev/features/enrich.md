---
title: Enrich (filling missing details)
order: 50
updated: v0.7
---
**What it does:** fills a contact's empty fields.

## How it works
`jobs.enrich(record_id, steps)` uses the fields of all directories the contact is in (or waiting for), then steps from `methods.ENRICH_STEPS`: eBay store lookup → find own website → company website (home, Contact / About / Impressum, sitemap; code first, then AI with `ENRICH_PROMPT` on missing fields only) → social links → other pages and search snippets. Only empty fields are filled; the source page is stored per field.

## Who may enrich
`contacts.may_enrich()`: the *Enrich* permission, and for contacts someone else found first also *Enrich other people's contacts* (v0.7).

## Started from
Card button, big card **Enrich Now**, list **Enrich Selected**, Inbox **Enrich**, **Enrich All Incomplete** (50 least complete), Dashboard *Enrich Them*, night run.

## Files
`app/jobs.py → enrich`, `app/crawl.py`, `app/extract.py`.
