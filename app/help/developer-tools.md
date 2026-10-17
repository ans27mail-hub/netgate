---
title: Developer tools
section: Developers
order: 20
needs: debug, logs, tester, training_export, dev_help
summary: Debug view, logs, page tester, training data
---
On the left: **Developer Tools**.

- **Developer Handbook** — everything about how NetGate works, for developers: features, technologies, containers, database, AI prompts, weak points, ideas. Some pages are made automatically from the code, so they are always right. **Ask the Handbook** answers questions from it. Needs *Developer help* (Admin and Developer by default).

- **Debug View** — on the Requests page each request has a **Debug** button. It shows every search, every page read (with its text), what code found, and every question to the AI with its answer. Traces are kept 14 days; switch recording on or off on the Developer Tools page.
- **Logs** — NetGate's own log: errors from the web app, workers and scheduler, with full details. Logs of the containers themselves (browser, database) are in WSL: `docker compose logs --tail 50 <service>`.
- **Page Tester** — try any page with a directory's instructions. Nothing is saved.
- **Training Data** — download all accept / reject decisions as JSONL for fine-tuning.
