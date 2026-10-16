---
title: Search methods
section: Directories & searching
order: 30
summary: Web search, Directory site, eBay, Company website
---
A directory can use several methods. Each knows how its site works.

| Method | What it does | Needs |
|---|---|---|
| **Web search** | Searches the web (your own search engine, SearXNG), reads list and company pages, follows next pages and directory profiles. | nothing |
| **Directory site search** | Reads B2B directory sites you name: their list pages (put `{q}` where the keyword goes in a site's search address) or sites searched with *site:*. Profiles and next pages are always followed. | list pages or sites |
| **eBay search** | Uses eBay's official API: searches listings on the chosen marketplaces, groups them by seller, then reads each seller's details (business name, address, email, phone, VAT, rating, feedback). | eBay keys in Settings → Connections |
| **Company website (Enrich)** | Reads each company's own site: Contact, About, Impressum, sitemap. | nothing |
| Etsy search | Later version | Etsy keys |
| Amazon search | Later version (through search results; limited) | — |
| Custom recipe | Later: a site of your own choice with its own reading rules, added through an update | — |

New methods and site recipes are added in code through GitHub updates, never typed into the web page — that keeps NetGate safe and the same for everyone.

## eBay in short
- *Business sellers only* skips private sellers. On marketplaces where eBay can't filter this in the search, NetGate checks each seller.
- The same seller is recognised by its eBay name, so it is never added twice.
- eBay limits how many calls a key may make per day (see your limits on developer.ebay.com). One keyword uses one call per 200 listings, plus one per seller.
