---
title: Technologies
order: 20
updated: v0.7
---
| Part | What | Why it was chosen |
|---|---|---|
| **Python 3.12 + FastAPI** | The web app (`app/main.py`, `app/web/`) | Simple, fast, good for an AI to maintain |
| **Jinja2 templates + HTMX 2** | Pages are rendered on the server; HTMX swaps small parts (open card, Running Jobs, help window) | No JavaScript build step; works without a front-end framework. HTMX is served locally (`app/static/htmx.min.js`) |
| **PostgreSQL 16** | All data, JSONB for flexible fields (`records.data`) | Reliable; JSON columns for per-directory fields |
| **SQLAlchemy 2** | Database models in `app/db.py` | Clear models, works with Postgres JSONB |
| **Redis 7 + RQ** | Job queue: `netgate` (daytime) and `netgate-night` | Small and simple background jobs |
| **SearXNG** | Own search engine (port 8888 on the PC) | Free, no API key; queries public engines |
| **Playwright Chromium** (`renderer/`) | Opens pages that need JavaScript, returns the HTML | Real browser for modern sites |
| **trafilatura** | Turns HTML into readable text | Good main-text extraction |
| **Ollama** (iMac, model `qwen3:8b`) | The AI that reads pages and answers in JSON | Runs locally, no cost per page |
| **OpenRouter** (optional) | Paid cloud models with spending limits | Fallback / bigger models later |
| **numpy** | Word-hash vectors for AI suggestions | Fast similarity without a model |
| **Python-Markdown** | Help Center and this Handbook | Pages are plain `.md` files in GitHub |
| **Docker Compose in WSL** | Runs everything on the owner's Windows PC | One command to update: `netgate update` |
| **eBay Browse API** | eBay seller search | Official, allowed, structured data |

Fonts: Instrument Sans (UI) and JetBrains Mono (addresses, codes), loaded from Google Fonts; a theme can choose another font.
