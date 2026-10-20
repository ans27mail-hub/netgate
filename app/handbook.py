"""The Developer Handbook (Developer Tools → Handbook, permission “Developer help”).

Two kinds of pages:
- written pages in docs/dev/*.md and docs/dev/features/*.md (explanations; kept up to date with every change);
- automatic pages built from the code each time they are opened (routes, tables, permissions, settings, AI prompts,
  versions), so those can never be out of date.

Every feature in FEATURES must have docs/dev/features/<slug>.md (a test checks this). Each written page has
front matter with `title`, `order` and `updated: v0.x`.
"""
import os
import re

import markdown

ROOT = os.path.dirname(os.path.dirname(__file__))
DEV_DIRS = [os.path.join(ROOT, "docs", "dev"), "/code/docs/dev"]

# slug -> title. One written page per feature, under docs/dev/features/.
FEATURES = {
    "dashboard": "Dashboard", "directories": "Directories and the directory page", "discovery": "Discovery (finding companies)",
    "search-methods": "Search methods", "ebay": "eBay search", "inbox": "Inbox and decisions", "learning": "AI suggestions (learning)",
    "enrich": "Enrich (filling missing details)", "contacts": "Contacts, cards and the big card", "add-contact": "Adding contacts by hand",
    "move-contacts": "Moving contacts between directories", "tags": "Tags", "cards": "Card styles and short-card fields",
    "requests": "Requests (pause, stop, delete, reject)", "night-run": "Night run", "people": "People: users, roles, logins, passwords",
    "visibility": "What each person sees (own contacts, directories, methods)", "themes": "Themes", "backups": "Backups",
    "help-center": "Help Center", "developer-tools": "Developer Tools and this Handbook", "crawler": "Crawler and renderer",
    "search-engines": "Search engines (SearXNG engines, status, log)",
    "pages-read": "List of pages read (skip and reuse)",
    "keyword-library": "Keyword Library, translations and the Search Builder", "browser-search": "Browser search and Solve CAPTCHA Yourself",
    "company-page": "Company page, Verify, profile and products", "testing-guide": "Testing Guide (checklists, runs, Test Directory)",
}
AUTO = {
    "auto-routes": "Pages and addresses (automatic)", "auto-database": "Database tables (automatic)",
    "auto-permissions": "Permissions (automatic)", "auto-settings": "Settings and defaults (automatic)",
    "auto-prompts": "AI prompts (automatic)", "auto-versions": "Versions and components (automatic)",
}


def _dev_dir() -> str | None:
    return next((d for d in DEV_DIRS if os.path.isdir(d)), None)


def _parse(path: str, slug: str, kind: str) -> dict:
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return {"slug": slug, "title": meta.get("title") or slug.replace("-", " ").capitalize(), "kind": kind,
            "order": int(meta.get("order") or 50), "updated": meta.get("updated") or "", "body": body}


def written() -> list[dict]:
    d = _dev_dir()
    out = []
    if not d:
        return out
    for f in sorted(os.listdir(d)):
        if f.endswith(".md"):
            out.append(_parse(os.path.join(d, f), f[:-3], "guide"))
    fd = os.path.join(d, "features")
    if os.path.isdir(fd):
        for f in sorted(os.listdir(fd)):
            if f.endswith(".md"):
                out.append(_parse(os.path.join(fd, f), "feature-" + f[:-3], "feature"))
    out.sort(key=lambda p: (p["kind"] != "guide", p["order"], p["title"]))
    return out


def missing_features() -> list[str]:
    have = {p["slug"][8:] for p in written() if p["kind"] == "feature"}
    return [f for f in FEATURES if f not in have]


def html(text: str) -> str:
    # Python-Markdown needs a blank line before a list; add it so “text:\n- item” renders as a list.
    text = re.sub(r"(?m)^(?![ \t]*(?:[-*]|\d+\.)[ \t]|[ \t]*$)(.+)\n(?=[ \t]*(?:[-*]|\d+\.)[ \t])", r"\1\n\n", text)
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"])


# ---------- automatic pages ----------

def _flat_routes(routes):
    """Routes, also inside included routers (newer FastAPI versions wrap them)."""
    for r in routes:
        inner = getattr(getattr(r, "original_router", None), "routes", None)
        if inner is not None and not getattr(r, "path", ""):
            yield from _flat_routes(inner)
        else:
            yield r


def auto_routes(app) -> str:
    rows = []
    for r in _flat_routes(app.routes):
        path = getattr(r, "path", "")
        if not path or path.startswith(("/openapi", "/docs", "/redoc", "/static")):
            continue
        methods = ", ".join(sorted(getattr(r, "methods", None) or [])) or "—"
        ep = getattr(r, "endpoint", None)
        where = f"{ep.__module__.replace('app.', '')}.{ep.__name__}" if ep else ""
        doc = ((ep.__doc__ or "").strip().splitlines() or [""])[0] if ep else ""
        rows.append((path, methods, where, doc))
    rows.sort()
    out = ["Every address the web app answers, with the code that handles it.\n", "| Address | Method | Code | What |",
           "|---|---|---|---|"]
    out += [f"| `{p}` | {m} | `{w}` | {d} |" for p, m, w, d in rows]
    return "\n".join(out)


def auto_database() -> str:
    from .db import Base
    out = ["All tables and columns, from the code (`app/db.py`). Upgrades for existing installs are in `MIGRATIONS` "
           "and the one-time `_upgrade_v0x` steps.\n"]
    for name, table in sorted(Base.metadata.tables.items()):
        out.append(f"### `{name}`")
        out.append("| Column | Type | Notes |\n|---|---|---|")
        for c in table.columns:
            notes = []
            if c.primary_key:
                notes.append("key")
            for fk in c.foreign_keys:
                notes.append(f"→ `{fk.target_fullname}`" + (f" ({fk.ondelete.lower()})" if fk.ondelete else ""))
            if c.index:
                notes.append("indexed")
            if c.unique:
                notes.append("unique")
            out.append(f"| `{c.name}` | {str(c.type).lower()} | {' · '.join(notes)} |")
        out.append("")
    return "\n".join(out)


def auto_permissions() -> str:
    from .auth import DEFAULT_ROLES, DIR_PERMS, PERM_GROUPS
    out = ["From `app/auth.py`. *Directory* permissions also need access to that directory.\n",
           "| Group | Key | Name | What it allows | Directory | Default roles |", "|---|---|---|---|---|---|"]
    for glabel, items in PERM_GROUPS:
        for key, label, desc in items:
            roles = ", ".join(n for n, _, perms in DEFAULT_ROLES if key in perms)
            out.append(f"| {glabel} | `{key}` | {label} | {desc} | {'yes' if key in DIR_PERMS else ''} | {roles} |")
    return "\n".join(out)


def auto_settings() -> str:
    from . import backups, crawl, jobs, methods
    from .web.common import DISPLAY_DEFAULTS
    blocks = [("display", "Settings → Display (and per person in user prefs)", DISPLAY_DEFAULTS),
              ("crawler", "Settings → Crawler", crawl.CRAWLER_DEFAULTS),
              ("night", "Settings → Night Jobs", jobs.NIGHT_DEFAULTS),
              ("backups", "Settings → Backups", backups.DEFAULTS),
              ("connections", "Settings → Connections (secrets are never shown back)", methods.CONNECTION_DEFAULTS),
              ("(directory) methods.ebay", "Directory Settings → eBay search", methods.EBAY_DEFAULTS),
              ("(directory) methods.directory", "Directory Settings → Directory site", methods.DIRECTORY_DEFAULTS)]
    out = ["Stored as JSON in `app_settings` (key → value). Defaults from the code:\n"]
    for key, where, d in blocks:
        out.append(f"### `{key}` — {where}")
        out.append("| Setting | Default |\n|---|---|")
        for k, v in (d or {}).items():
            shown = "(secret)" if any(x in k for x in ("secret", "key", "token")) else repr(v)
            out.append(f"| `{k}` | `{shown}` |")
        out.append("")
    out.append("Other keys: `ai.<job>` (server + model per job), `ai.fallback`, `ai.limits`, `learn`, `dev` (debug "
               "traces on/off), `theme` (theme for everyone), `themes` (custom themes), `backups.request`, "
               "`backups.status`, and upgrade flags (`v05_upgraded`, `v07_upgraded`, `roles_seeded` …).")
    return "\n".join(out)


def auto_prompts() -> str:
    from . import jobs
    out = ["The exact instructions NetGate sends to the AI (from `app/jobs.py`). `{…}` parts are filled in for each "
           "page or company. The AI must answer with JSON only.\n"]
    for name in sorted(n for n in dir(jobs) if n.endswith("_PROMPT")):
        out.append(f"### `{name}`\n```\n{getattr(jobs, name)}\n```")
    out.append("The Help and Handbook answers use a short prompt in `app/help.py` / `app/handbook.py` "
               "(answer only from the pages given).")
    return "\n".join(out)


def auto_versions() -> str:
    from .web.common import VERSION
    out = [f"NetGate **{VERSION}**.\n", "### Python packages (`requirements.txt`)"]
    for path in (os.path.join(ROOT, "requirements.txt"), "/code/requirements.txt"):
        if os.path.exists(path):
            out += [f"- `{line.strip()}`" for line in open(path) if line.strip() and not line.startswith("#")]
            break
    for path in (os.path.join(ROOT, "docker-compose.yml"), "/code/docker-compose.yml"):
        if os.path.exists(path):
            out.append("\n### Containers (`docker-compose.yml`)")
            svc = None
            for line in open(path):
                m = re.match(r"^  ([a-z0-9-]+):\s*(#.*)?$", line)
                if m:
                    svc = m.group(1)
                    out.append(f"- **{svc}**" + (f" — {m.group(2)[1:].strip()}" if m.group(2) else ""))
                im = re.match(r"^    image:\s*(\S+)", line)
                if im and svc:
                    out[-1] += f" · image `{im.group(1)}`"
                if re.match(r"^    build:", line) and svc:
                    out[-1] += " · built from this repository"
            break
    out.append("\nThe AI (Ollama) runs outside Docker, on the owner's iMac. The Dockerfiles are `Dockerfile` (app) "
               "and `renderer/Dockerfile` (Chromium, Debian 12 bookworm).")
    return "\n".join(out)


def auto_page(slug: str, app) -> str:
    return {"auto-routes": lambda: auto_routes(app), "auto-database": auto_database,
            "auto-permissions": auto_permissions, "auto-settings": auto_settings, "auto-prompts": auto_prompts,
            "auto-versions": auto_versions}[slug]()


# ---------- search & ask ----------

def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(w) > 2]


def search(query: str, limit: int = 6) -> list[dict]:
    q = set(_words(query))
    scored = []
    for p in written():
        title, body = set(_words(p["title"])), _words(p["body"])
        score = 3 * len(q & title) + sum(1 for w in body if w in q) / max(1.0, len(body) ** 0.5)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:limit]]


def ask(question: str) -> dict:
    from . import ai
    found = search(question, 3)
    if not found:
        return {"answer": "", "sources": [], "error": "No Handbook page mentions that yet. Try other words."}
    context = "\n\n".join(f"### [{p['slug']}] {p['title']}\n{p['body'][:6000]}" for p in found)
    prompt = ("You answer a developer's question about NetGate using ONLY the handbook pages below. "
              "If they don't answer it, say so. Be short and precise; name files and functions when useful.\n\n"
              f"{context}\n\nQuestion: {question}\n\n"
              'Return JSON only: {"answer": "...", "pages": ["slug of each page you used"]}')
    try:
        data = ai.ask_json("help", prompt, timeout=150) or {}
    except Exception as e:
        return {"answer": "", "sources": found, "error": f"The AI could not be reached ({type(e).__name__}). "
                                                         "These pages may answer it:"}
    used = [p for p in found if p["slug"] in (data.get("pages") or [])] or found
    return {"answer": str(data.get("answer") or "").strip(), "sources": used, "error": ""}
