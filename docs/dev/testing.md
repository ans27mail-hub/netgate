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
| `tests/test_v07.py` | v0.6 → current: tags, card styles, short-card fields, themes, own contacts / directories, Existing Contacts, See Search Methods, enrich others, debug page, Running Jobs, backups (with the real `backup/run.sh`), Handbook (every feature has a page), Title Case |

Each test ends with **ALL PASSED** or a list of failures, and checks that NetGate's log has no errors.

After changing pages, also take screenshots (Playwright) of the changed pages at 1440 px and 390 px (phone): the tests check content, not looks.
