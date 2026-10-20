---
title: Testing
order: 70
updated: v0.7
---
End-to-end tests run the real code against a real PostgreSQL, a fake website (`tests/fakeweb.py`: `dir.test`, `jsdir.test`, `acme.test`, `beta.test`), a fake eBay API (`tests/fake_ebay.py`, port 3998) and the real renderer (port 3999). The search engine and the AI are simulated inside the tests, so results are repeatable. See `tests/README.md` for the commands.

| Test | Covers |
|---|---|
| `tests/test_v05.py` | v0.4 → current upgrade; Discover → Inbox, accept / reject / restore, several directories, suggestions, eBay, pause / resume / stop / reject / delete, add contact, roles, help, night run |
| `tests/test_v06.py` | v0.5 → current: Dashboard, Directories page, switcher, moving contacts, People (users, roles, logins, passwords) |
| `tests/test_v09.py` | v0.8 → current: stuck requests (worker start, 30 min, Force Stop), pages read (skip per directory, 0 days, earlier tries, Enrich reuse, Check All Again, Debug, big card), Directory Settings → Enrich and the searches it builds, Enrich Now ▾, new permissions and Cards Only, colour sets / fonts / uploaded fonts / My Look, pop-ups |
| `tests/test_v08.py` | v0.7 → current: delete only empty directories, Fill the row, Edit and Run Again (tries, Go Deeper, Save as Keyword, nothing-found hint, permissions), Search Engines (on / off, status, blocking since, Test Now, Debug engines, Dashboard warning) |
| `tests/test_v07.py` | v0.6 → current: tags, card styles, short-card fields, themes, own contacts / directories, Existing Contacts, See Search Methods, enrich others, debug page, Running Jobs, backups (with the real `backup/run.sh`), Handbook (every feature has a page), Title Case |

Each test ends with **ALL PASSED** or a list of failures, and checks that NetGate's log has no errors.

After changing pages, also take screenshots (Playwright) of the changed pages at 1440 px and 390 px (phone): the tests check content, not looks.
