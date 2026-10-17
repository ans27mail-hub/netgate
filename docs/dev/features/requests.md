---
title: Requests (pause, stop, delete, reject)
order: 80
updated: v0.7
---
**What it does:** every search and enrich is a request with tabs All · Running · Waiting · Paused · Done · Failed · Stopped · Rejected · Deleted, and actions Pause, Resume, Stop, Delete (bin 30 days), Reject (keyword to the reject list), Run Again, bulk and Pause All.

## How it works
- `control.py`: actions set `jobs.control` (pause / stop) which `Ctx.check()` reads; Resume re-queues with the saved `jobs.state`.
- **Requests are a separate layer**: deleting / rejecting never changes contacts.
- Reject list matching: lower case, word order, plurals and small words ignored; similar keywords only warn.
- **Debug view** (`/requests/<id>/debug`, permission *Debug view*): searches, pages read (text), code finds, AI questions and answers, Inbox items made. v0.7: the same action buttons, **← Back to Requests**, **Clear Debug Notes**.

## Files
`app/control.py`, `app/web/requests_routes.py`, `templates/requests.html`, `debug.html`.
