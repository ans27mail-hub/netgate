---
title: Working on NetGate (rules and the owner)
order: 15
updated: v0.7
---
## The owner
**Abdul Moeez** (Motofast International). Not a programmer: explain in plain words, short sentences. He installs every version himself with `netgate update` in WSL.

## How changes are agreed
1. He describes an idea. You **explain or draw a mockup first** (the design canvas has boards D, D2 … D6).
2. Only when he says **"build"** (e.g. "build v0.8") is code changed.
3. Versions are **v0.x**. Each release: tests pass → `docs/ROADMAP.md`, `docs/DECISIONS.md`, `CHANGELOG.md` and this Handbook updated → commit → line at the top of `releases.txt` → push to `main`.

## Rules for the code
- Keep existing data. Upgrades: `MIGRATIONS` (idempotent SQL) + one-time `_upgrade_v0x` steps with a flag in `app_settings`.
- Every page has a `help=` slug and a page in `app/help/`. Every feature has a page in `docs/dev/features/` (a test checks the list in `app/handbook.py → FEATURES`).
- API secrets are never shown back on a page.
- Plain-English UI, **Title Case** for headings, menus, tabs and buttons ("Run Discovery", "Existing Contacts").
- Accessible HTML (labels, aria), works on a phone.
- Search methods and site recipes are code only.
- The Handbook never contains passwords or keys.
