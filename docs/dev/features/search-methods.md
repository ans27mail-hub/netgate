---
title: Search methods
order: 35
updated: v1.0
---
**What it does:** a directory chooses how it finds companies: **Web search**, **Directory site search**, **eBay search** (find step) and **Company website** (enrich step). Etsy, Amazon and Custom recipe are shown as “later”.

## How it works
- Registry in `app/methods.py → METHODS` (name, step, tag, kind, ready). A directory's choice and options are in `groups.methods` (JSON).
- Keywords can be tied to one method (`keywords.method`) or all.
- **See search methods** (v0.7): only people with this permission (or *Manage directories*) see method badges, the method choice in Run Discovery, method columns and Inbox method labels. Others search with all methods without seeing them.

## Rules
Methods are **code** (added through GitHub), never editable in the web page.

## Files
`app/methods.py`, `templates/_dir_methods.html`, `app/auth.py → sees_methods()`.

## v1.0
New method `browser` (find; options `want`, `max_pages`, `max_minutes`, `engines`, defaults in `methods.BROWSER_DEFAULTS`) — see *Browser search*.
