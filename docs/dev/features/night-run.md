---
title: Night run
order: 85
updated: v1.0
---
**What it does:** in a time window (default off, 23:00–07:00, Asia/Karachi) runs each directory's night keywords (Discover) and enriches contacts (flagged → incomplete → new Inbox → refresh), up to a maximum, with a pause between companies.

## How it works
`scheduler.tick()` starts a `night` job on queue `netgate-night`; `jobs.run_night()` skips rejected keywords and ones already run tonight and stops at the window's end. Results in Settings → Night Jobs and the Dashboard tile.

## Files
`app/scheduler.py`, `app/jobs.py → run_night`, `templates/night.html`.

## v1.0
Step 4: Verify contacts whose `records.meta._verified` is older than `verify_months` (Night Jobs; 0 = off), at most `verify_max`; counted in `stats.verified`. Night keywords carry `term_ids` / `lang` and search through `jobs.search_words()`.
