# AGENTS.md — start here

You are continuing **NetGate**, a self-hosted web app that builds business directories with a local AI.
This file is for any AI assistant or developer picking up the project. Read it fully, then the files it points to.

## Read first (in this order)
1. `docs/PROJECT.md` — what NetGate is for, who uses it, the owner's setup.
2. `docs/ROADMAP.md` — what is done (per version) and what comes next.
3. `docs/DECISIONS.md` — choices already made and why. **Don't undo a decision without asking the owner.**
4. `docs/ARCHITECTURE.md` — how the code fits together; where to change what.
5. `docs/DESIGN.md` — the layout direction and screenshots.
6. `CHANGELOG.md` — what changed in each version, in plain words (also shown in the app under Help → What's new).

## How the owner likes to work
- The owner is **Abdul Moeez** (Motofast International, Sialkot). He is not a programmer: explain in plain words, short sentences, no jargon.
- **Explain or show a mockup first. Build only when he says “build”** (e.g. “build v0.6”). “Suggest”, “what do you think”, “show me” mean: don't change code.
- Ask only when a wrong guess would be costly; otherwise use a sensible default and write it in `docs/DECISIONS.md`.
- Versions are **v0.x** (v0.5, v0.6 …), never random numbers.
- He updates his server himself with `netgate update` in WSL, so every release must install with that one command.

## Rules for the code
- **Keep existing data.** Database changes are upgrades in `app/db.py`: idempotent statements in `MIGRATIONS` plus one-time steps guarded by a flag in `app_settings` (see `_upgrade_v05`). Never drop user data.
- **Search methods and site recipes are code**, added through GitHub — never editable in the web UI.
- **API secrets are never shown back** on a page (only “saved”). Empty input keeps the saved value; “-” removes it.
- **Requests are a separate layer:** deleting or rejecting a request never changes contacts.
- **Nothing reaches a directory without being accepted** (except “accept straight away” by a person who may review).
- Code first, AI second: anything plain code can find reliably (emails, phones, links, schema.org) is not asked from the AI.
- Every new page gets a `help=` slug and a help page in `app/help/` (Markdown). Keep help in step with the code.
- Plain-English UI text. Accessible HTML (labels, aria where needed). Works on a phone.

## Releasing a version
1. Test (see “Testing” in `docs/ARCHITECTURE.md`). The end-to-end tests in `tests/` must pass.
2. Update **`docs/ROADMAP.md`, `docs/DECISIONS.md` and `CHANGELOG.md`** — every work session, before pushing. This is what keeps this handover current.
3. Commit, then add a line at the top of `releases.txt`: `v0.x  <commit>  <YYYY-MM-DD>  <short description>`, commit and push to `main`.
4. Tell the owner to run `netgate update` (and anything special, e.g. a longer first build).
   `netgate rollback` goes back one version; `netgate versions` lists them.

## Starting a new session
The owner will paste something like:
> “Read AGENTS.md in github.com/ans27mail-hub/netgate and continue the project. Next: v0.7.”

Then: read the files above, check `docs/ROADMAP.md` → *Next*, explain the plan in plain words, and wait for “build”.
