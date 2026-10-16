# Decisions

A dated log of choices and why. Newest first within each date. Don't undo one without asking the owner.

## 2026-10-16 (v0.5)
- **Requests are a separate layer.** Deleting or rejecting a request never changes contacts, their data, sources or Inbox items. Each contact keeps a plain-text history note (“Found by Web search ‘glove makers’ · 16 Oct 2026 · admin”), so it still makes sense after the request is gone. The database link from a contact to its request is cleared, never cascaded. *(Owner's request.)*
- **Deleted requests** go to a Deleted tab for 30 days (restorable), then the scheduler removes them. There is no “also delete contacts” option. Contacts are only removed on purpose (Inbox, or a contact's card).
- **Reject a request** = stop it (if running) + put its keyword on the reject list with a reason. Contacts it found are not rejected; they wait in the Inbox as usual.
- **Reject list matching:** exact keyword after normalising (lower case, word order, plurals, small words like “the / top / list” ignored). Similar keywords (Jaccard ≥ 0.5) only get a warning. *(Default chosen; owner didn't decide.)*
- **Inbox before directory:** nothing found by a search reaches a directory until a person accepts it. Hand-added contacts also go to the Inbox, unless a person who may review ticks “accept straight away”.
- **One contact, many directories:** a contact exists once (`records`) and belongs to directories through `memberships`. Inbox items are per (contact, directory). Once a contact has an Inbox item for a directory (waiting, accepted or rejected), later searches don't suggest it again for that directory — rejected stays rejected.
- **Matching the same company:** marketplace id (e.g. eBay seller name) → website domain → name (+ city). Across all directories.
- **Groups became directories** (the code and tables still say `group`). v0.4 listings became accepted members of their group; nothing was lost. Keywords stay with their directory and are shown in the Inbox.
- **Suggestions, not decisions:** “AI suggests …%” is a nearest-neighbour vote over past accept / reject decisions for the same directory (word-hash vectors by default, Ollama embeddings optional). It never decides on its own. Real fine-tuning is later, from the exported decisions.
- **Roles:** Admin (locked, everything), Manager, Researcher, Viewer, Developer. Changing a role changes everyone with it. **Per-person exceptions allowed**, shown with a “custom” badge. **Directory access is per person**, with a default from the role. *(Defaults chosen; owner didn't decide.)* Existing users got the closest role, with exceptions so they keep exactly their v0.4 access. The old `users.perms` column is still written (v0.4 names) so a rollback keeps working.
- **Developer role** = tools inside the app (debug trace, app log, page tester, training export, developer help). Code changes only through GitHub. No access to users or API keys by default.
- **Container logs** are not read from the web app (that would need the Docker socket, a security risk). NetGate writes its own log table; container logs stay in WSL (`docker compose logs`).
- **eBay search uses the official Browse API** (client-credentials token). Business sellers only by default; where eBay rejects the business filter (e.g. some marketplaces) the search is retried without it and each seller's account type is checked. Seller page link: `https://www.<site>/usr/<seller>`.
- **Etsy, Amazon and Custom recipes** are shown as “later” in the method list, not built yet.
- **Help lives in the repository** (`app/help/*.md`) and ships with each version; it is not editable in the UI. Pages can be limited to people with certain permissions (`needs:`).
- **Handover files** (`AGENTS.md`, `docs/`) are updated every work session. `CLAUDE.md` only points to `AGENTS.md`.
- Database upgrades take a Postgres advisory lock, because the web app and the scheduler both start them.

## 2026-10-16 (v0.4)
- The headless browser runs in its own container (`renderer`, Playwright Chromium on Debian 12 “bookworm” — Playwright 1.48 can't install its dependencies on Debian 13 “trixie”). It runs 24/7 for night jobs, is separate from the owner's own Chrome, memory-capped, and updates with the app. Used only when a page needs it (“auto”).
- Polite crawling: robots.txt, 2 s per-site delay, one retry. Cache 3 days.
- Code-first extraction; the AI is only asked for what code couldn't find.
- API secrets are never displayed; empty input keeps the saved value, “-” removes it.
- eBay default marketplaces: UK, DE, IT, FR, USA, Canada.

## 2026-10-15 (v0.1–v0.3)
- Stack: Python FastAPI + Jinja2 + HTMX, PostgreSQL, Redis + RQ workers, SearXNG, Ollama on the iMac. Docker in WSL on the owner's PC.
- Updates through GitHub: `netgate update` / `rollback` read `releases.txt` (git tags can't be pushed from the AI's environment).
- Version numbers are v0.x.
- Layout direction “D” (dark top, cards), later D4 (left sidebar) — see `docs/DESIGN.md`.
- Scripts / methods are never editable in the web UI.
- Night jobs run in a time window and stop by themselves; a separate night worker so daytime jobs don't wait.
- OpenRouter optional, with spending limits and a fallback to Ollama.
