---
title: Settings explained
section: Settings
order: 10
summary: AI servers, crawler, display and the reject list
---
## AI servers & models
- **Servers** — your Ollama servers (the iMac, later a GPU PC) and optionally OpenRouter (paid, with spending limits).
- **Model for Each Job** — Discover, Enrich, Night jobs, Help answers, and a Fallback used when OpenRouter is off or over its limit.
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
| Read list pages again after | 7 days | A list page already read for the same directory is skipped for this long (0 = always read again). See [Pages read](/help/pages-read) |

## Search Engines
Which engines web searches use, whether each one works or is blocking (and since when), and how many links each gave. See [Search engines](/help/search-engines).

## Display
**My Look** — your own colours, fonts and text size (see [Themes](/help/themes)).
Page width (fixed, % of the screen, or full), grid or list by default, **Cards** (style A / B / C, card width, **Fill the row**, colour from tags) and **at most N cards per row** — for you, or for everyone (with *Display & themes for everyone*). **My theme** chooses a [theme](/help/themes) just for you.

## Tags, Themes, Backups
See [Tags](/help/tags), [Themes](/help/themes) and [Backups](/help/backups).

## Reject list
Keywords that are never searched. See [Requests](/help/requests).
