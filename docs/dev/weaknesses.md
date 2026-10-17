---
title: Weaknesses and risks
order: 90
updated: v0.7
---
An honest list, most important first. Update it when something is fixed or found.

1. **One PC runs everything.** If the PC sleeps, restarts or WSL stops, NetGate and the night run stop. Backups (v0.7) protect the data, but not uptime.
2. **Backups are on the same PC unless `BACKUP_DIR` points elsewhere.** Put them on a second disk or a share. A restore test hasn't been done by the owner yet.
3. **No HTTPS on the office network, no two-step login.** Passwords travel in plain HTTP inside the LAN. Planned: Authentik (one login for all factory apps, 2FA) and HTTPS.
4. **The AI is small (qwen3 8B).** It misses companies, mixes up cities, sometimes invents. The Inbox (people decide) and code-first extraction limit the damage.
5. **Web pages change; sites block robots.** A method can stop working without warning. The debug view shows where; recipes per site are planned (Scanner).
6. **SearXNG depends on public search engines**, which can rate-limit or block it.
7. **Scale.** Lists load up to 500 contacts; completeness and some counts are computed in Python. Thousands of contacts per directory will get slower (fix: counts in SQL, Postgres full-text search).
8. **Tests use a fake web and a fake eBay.** Real sites behave differently.
9. **Built with an AI.** Knowledge lives in this Handbook, `docs/` and the tests — keep them current, or the next person (or AI) won't know why things are the way they are.
10. **Sessions** last 14 days on a computer; a shared office PC should log out.
11. **Images and text from other companies** are for internal use only.
