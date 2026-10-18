---
title: Search engines
section: Settings
order: 25
summary: Which search engines are used, which work or block, and since when
needs: crawler
---
NetGate's web searches go through its own search box (**SearXNG**), which asks several search engines at once — Google, Bing, DuckDuckGo, Brave and others. Search engines sometimes **block** automated searches (they show a CAPTCHA). **Settings → Search Engines** shows what is happening and lets you choose.

## The list
| Column | What it means |
|---|---|
| **On** | Switch an engine on or off, then press **Save**. At least one must stay on. |
| **Status** | **Working** — its last search went fine. **Blocking** — it refused (CAPTCHA, access denied, too many searches), with *since when* and the reason. **Not Answering** — it timed out or gave an error. **Not Used Yet** — no search has asked it. |
| **Last 7 Days** | How many links it gave, in how many searches, and how many times it failed. |
| **Last Worked** | When it last answered properly. |

*default* marks the engines SearXNG uses by itself. Until you press **Save**, SearXNG decides; after saving, NetGate decides. **Use SearXNG's Defaults** goes back.

## Test Now
Type a search and press **Test Each Engine**: every engine that is on is asked once, on its own. The result shows next to each engine (number of links, or the reason it failed).

## Recent searches
The last searches with the number of links from each engine and which engines failed. A search made by a request links to its Debug page. Searches are kept for 30 days.

## Good to know
- A blocking engine usually starts working again after some hours. NetGate never solves CAPTCHAs.
- The **Dashboard** warns when an engine that is on has been blocking, and the System status shows how many are blocking.
- In a request's **Debug** page, each link shows which engine(s) gave it.
- Paid backup search services (Brave, Google, Serper keys) are planned for later.
