---
title: Settings explained
section: Settings
order: 10
summary: AI servers, crawler, display and the reject list
---
## AI servers & models
- **Servers** — your Ollama servers (the iMac, later a GPU PC) and optionally OpenRouter (paid, with spending limits).
- **Model for each job** — Discover, Enrich, Night jobs, Help answers, and a Fallback used when OpenRouter is off or over its limit.
- **Learning** — an optional embedding model for better Inbox suggestions.

## Crawler
| Setting | Safe value | What it does |
|---|---|---|
| Use the browser | auto | When to open pages in the hidden browser |
| Next pages | 4 | How many “next” pages of a list to follow |
| Directory mode / profiles per page | on / 15 | Open company profile pages on list pages |
| Site pages | 8 | Pages of a company's own site read by Enrich |
| Delay | 2 s | Wait between requests to the same site |
| Cache | 3 days | Keep downloaded pages this long |
| robots.txt | on | Follow each site's rules for crawlers |
| Parts per long page | 3 | Long pages are split into at most this many parts |

## Display
Page width (fixed, % of the screen, or full), grid or list by default, and cards per row — for you, or for everyone (with *Display for everyone*).

## Reject list
Keywords that are never searched. See [Requests](/help/requests).
