---
title: Search engines (SearXNG engines, status, log)
order: 47
updated: v0.8
---
**What it does:** Settings → Search Engines (permission *Crawler settings*) turns SearXNG's web engines on / off, shows whether each one is working or blocking (and since when), links per engine over the last 7 days, a **Test Now** per engine, and the recent searches. Free engines only; paid backup keys (Brave, Google, Serper) are for later.

## How it works
- `crawl.search(query, pageno, engines=None, test=False)` sends `engines=<comma list>` to SearXNG when NetGate has a choice (`engines.chosen()`, setting `search_engines` = `{"set": true, "on": [...]}`); without a choice SearXNG uses its own defaults. No SearXNG config change is needed — the `engines` parameter can use any engine SearXNG has loaded.
- Each result keeps `engines` (from SearXNG's `engines` / `engine`); `unresponsive_engines` (e.g. `["google", "CAPTCHA"]`) become the failed engines, kept in `crawl.last_search.errors` for the Debug trace.
- Every search is logged in `search_log` (`engines.record`, never raises): engines asked, links per engine, failures, request id (`crawl.set_search_job()` is set by `run_job`), test flag.
- `engines.status()` reads the last 30 days newest first: the first row that used an engine decides **working / blocking / error**; for failures, *since* is the first failure after the last success. Reasons with CAPTCHA, denied, too many, suspended, 403, 429 count as **blocking**.
- The engine list = known web engines (`engines.KNOWN`) found in SearXNG's `/config` (cached 10 min) + any other web engine SearXNG switches on; *default* marks SearXNG's own choice.
- Dashboard: `engines.problems()` → Needs Attention (“Google is blocking searches since …”) and System status “online · N engines blocking”.
- Debug: search traces carry `engines` (link → engines) and `blocked` (engine → reason).
- Scheduler: `control.purge_deleted()` also removes search-log rows older than 30 days.

## Files
`app/engines.py`, `app/crawl.py` (`search`), `app/web/engine_routes.py`, `templates/engines.html`, `debug.html`, `app/web/dashboard_routes.py`.

## Tests
`test_v08.py` with a fake SearXNG (`tests/fake_searx.py`): engine choice sent, CAPTCHA → Blocking since, recovery → Working, Test Now, Debug engines, Dashboard warning, at least one engine on.

## Limits & ideas
SearXNG's own rate limiting and engine suspension still apply. Later: paid backup engines with keys; Browser search (v0.9) for when all engines block.
