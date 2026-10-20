---
title: Testing Guide (checklists, runs, Test Directory)
order: 92
updated: v1.0
---
**What it does:** Menu → Testing Guide (permission `testing`, in Developer tools; admins have it). Step-by-step checklists for every feature; a person starts a test run (everything, or only the steps new in this version), marks each step Passed / Failed / Skipped with a note and screenshots, and copies a report of the failed steps. Runs are saved per version. Quick Health Check reads the state of every part without changing anything. The hidden Test Directory is a sandbox that one button empties.

## How it works
- Checklists are code: `app/testguide/<slug>.md` (front matter `title`, `feature`, `order`; numbered steps `N. (v1.0) Do this. => You should see this.`). `(v1.0)` marks the version that added a step. Parsed by `app/testguide.py` (`checklists`, `for_scope`, `counts`, `report`, `set_result`).
- **Rule:** every Handbook feature (`handbook.FEATURES`) has a checklist, and every version adds at least one step tagged with that version — `tests/test_v10.py` checks both, so a release without new checklist steps fails the tests.
- `app/web/testing_routes.py`: `/testing`, `POST /testing/runs`, `/testing/runs/{id}` (`?only=fail|todo`), `POST …/step` (HTMX, multipart with screenshot ≤5 MB png/jpeg/webp/gif), `…/finish|reopen|notes|delete`, `/testing/shots/{id}`, `/testing/health`, `POST /testing/test-directory/create|empty`.
- Test Directory: `groups.is_test`. `common.all_groups(s)` leaves it out (pass `with_test=True` to include it); All Contacts and the Inbox hide its contacts from people without `testing`; its own page needs `testing`. Empty: deletes its Inbox items and memberships, deletes contacts that are in no other directory and not waiting elsewhere, removes its requests (stopping running ones).

## Data
`test_runs` (user_id, version, scope all/new, results JSON {step id: {ok, note, by, at}}, notes, started_at, finished_at), `test_shots` (run_id, step, mime, data).

## Tests
`test_v10.py` (checklist rules, run, step results, screenshot, report, health check is read-only, Test Directory hidden and emptied, permission).
