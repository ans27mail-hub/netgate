---
title: Pages read
section: Using NetGate
order: 62
summary: NetGate keeps a list of every page it reads, and doesn't read the same pages again
---
NetGate keeps a permanent **list of every page it reads**: the address, when, which request read it, for which company, and what it found there (companies, emails, phones, social links, fields filled).

## What it is used for
- **Searching (Discover)** — a list page already read **for the same directory** in the last few days is **skipped**, so new searches spend their time on new pages. The number of days is in **Settings → Crawler → Read list pages again after** (0 = always read again). Another directory still reads the page.
- **Edit and Run Again** — pages read by **earlier tries of the same request** are always skipped.
- **Enrich** — a page already read **for that company** is not opened again; what was found there is reused. **Enrich Now ▾ → Check All Again** reads everything again.

## Where you see it
- A request's **Debug** page: *Pages Read by This Request*, and a note for every page skipped (“already read … by request #12”).
- An open contact card: **Pages Read** — the pages read for that company and where it was first found.
- The request's message says how many pages were skipped.

The list is the start of the **Saved Pages** part of NetGate, planned for later.
