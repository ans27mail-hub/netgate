---
title: Developer tools
section: Developers
order: 20
needs: debug, logs, tester, training_export, dev_help
summary: Debug view, logs, page tester, training data
---
On the left: **Developer tools**.

- **Debug view** — on the Requests page each request has a **Debug** button. It shows every search, every page read (with its text), what code found, and every question to the AI with its answer. Traces are kept 14 days; switch recording on or off on the Developer tools page.
- **Logs** — NetGate's own log: errors from the web app, workers and scheduler, with full details. Logs of the containers themselves (browser, database) are in WSL: `docker compose logs --tail 50 <service>`.
- **Page tester** — try any page with a directory's instructions. Nothing is saved.
- **Training data** — download all accept / reject decisions as JSONL for fine-tuning.
