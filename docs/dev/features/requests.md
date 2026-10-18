---
title: Requests (pause, stop, delete, reject)
order: 80
updated: v0.8
---
**What it does:** every search and enrich is a request with tabs All · Running · Waiting · Paused · Done · Failed · Stopped · Rejected · Deleted, and actions Pause, Resume, Stop, Delete (bin 30 days), Reject (keyword to the reject list), Run Again, bulk and Pause All.

## How it works
- `control.py`: actions set `jobs.control` (pause / stop) which `Ctx.check()` reads; Resume re-queues with the saved `jobs.state`.
- **Requests are a separate layer**: deleting / rejecting never changes contacts.
- Reject list matching: lower case, word order, plurals and small words ignored; similar keywords only warn.
- **Debug view** (`/requests/<id>/debug`, permission *Debug view*): searches, pages read (text), code finds, AI questions and answers, Inbox items made. v0.7: the same action buttons, **← Back to Requests**, **Clear Debug Notes**.

## Edit and Run Again (v0.8)
- Only Discover requests (`request` / `keyword`) that are done, failed or stopped (`control.can_edit`). Action `edit` → `/requests/<id>/edit` (`request_edit.html`).
- `control.edit_and_run()` keeps the finished try in `jobs.params.tries` (`n, query, group_id, methods, deeper, status, saved, updated, read, results, message, started, finished, by`), changes `query` / `group_id` / `params.methods` / `params.deeper`, sets `params.try` and `edited_by`, resets status / stats / state / counts and re-queues **the same job**. Inbox items of earlier tries keep their `job_id`; nothing is removed.
- A changed text or directory drops `keyword_id` (and a `keyword` job becomes `request`), so the keyword's counts stay right.
- `run_job` writes a trace note “Try N: …” at the start of each try.
- **Save as Keyword** (`/requests/<id>/save-keyword`, try `n`): adds the try's text to its directory's keywords; needs *Run keywords* for that directory or *Manage directories*; refuses rejected keywords and duplicates.
- Requests list: “Try N” badge, and “Nothing found — try different words or Go Deeper” for a finished Discover with 0 new / 0 updated.
- Plain **Run Again** still makes a new request; since v0.8 it keeps `methods` and `deeper`.
- Not yet: skipping pages read in earlier tries (needs the pages-read list, v0.9).

## Files
`app/control.py`, `app/web/requests_routes.py`, `templates/requests.html`, `request_edit.html`, `debug.html`.
