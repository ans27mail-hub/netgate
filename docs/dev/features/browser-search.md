---
title: Browser search and Solve CAPTCHA Yourself
order: 28
updated: v1.0
---
**What it does:** a search method (`browser`) that opens Bing / DuckDuckGo / Google result pages in NetGate's own headless browser (the renderer) like a person would, reads the result links and then reads those pages like Web search. When an engine shows a CAPTCHA, NetGate never solves it: it waits a few minutes for a person, shows them a live picture of the page in a pop-up, and passes their clicks and typing to that page. If nobody solves it (or they Give Up) the engine is paused for some hours.

## How it works
- `renderer/server.py`: one Playwright worker thread; `/render`, `/health`, and sessions `/session/open|state|shot|click|type|key|close` (by `sid`).
- `app/browser.py`: `ENGINES` (URL templates; override with env `BROWSER_ENGINE_URLS` JSON), settings in `app_settings["browser"]` (`engines`, `pause`, `per_hour`, `captcha_hours`, `wait_minutes`, `paused`), `is_captcha`, `result_links`, `searches_last_hour` (from the search log, `asked = ["browser:<engine>"]`), `wait_for_person` (a `captcha_waits` row; polls up to `wait_minutes`), `discover()` with the stop rules from the directory (`want`, `max_pages`, `max_minutes`).
- `app/web/browser_routes.py`: `POST /settings/browser`, `/captcha/mine` (JSON, polled every 6 s by `base.html`), `/captcha/{id}` (page; `frame=1` for the pop-up), `/captcha/{id}/shot`, `POST /captcha/{id}/click|type|key|giveup`.
- Dashboard Needs Attention: waiting CAPTCHAs and paused engines.

## Data
`captcha_waits` (job_id, user_id, engine, sid, url, status waiting/solved/gave_up, created_at, ended_at, solved_by). Method options in `groups.methods["browser"]`.

## Tests
`test_v10.py` with `tests/fake_engine.py` (port 3996: Bing-like results, a CAPTCHA page that a click solves).

## Limits & ideas
One browser page at a time (the renderer has one worker). Respect each engine's limits with the pause and per-hour settings.
