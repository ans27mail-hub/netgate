"""The Help Center: pages written in Markdown in app/help/, shown inside NetGate.

Each file starts with a small header:
    ---
    title: Review the Inbox
    section: Using NetGate          (groups pages on the Help home)
    order: 20
    needs: review                   (optional: only people with this permission see it)
    ---
The help is updated with the code (through GitHub), so it always describes the version you run.
"""
import os
import re

import markdown

HELP_DIR = os.path.join(os.path.dirname(__file__), "help")
CHANGELOG = [os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md"), "/code/CHANGELOG.md"]
SECTIONS = ["Start here", "Using NetGate", "Directories & searching", "Settings", "Troubleshooting", "Developers"]
_cache: dict = {}


def _parse(path: str) -> dict:
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    slug = os.path.splitext(os.path.basename(path))[0]
    return {"slug": slug, "title": meta.get("title") or slug.replace("-", " ").capitalize(),
            "section": meta.get("section") or "Using NetGate", "order": int(meta.get("order") or 50),
            "needs": meta.get("needs") or "", "summary": meta.get("summary") or "", "body": body,
            "html": markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists"])}


def pages() -> list[dict]:
    stamp = max([os.path.getmtime(os.path.join(HELP_DIR, f)) for f in os.listdir(HELP_DIR)] or [0]) \
        if os.path.isdir(HELP_DIR) else 0
    if _cache.get("stamp") != stamp:
        items = [_parse(os.path.join(HELP_DIR, f)) for f in sorted(os.listdir(HELP_DIR)) if f.endswith(".md")] \
            if os.path.isdir(HELP_DIR) else []
        items.sort(key=lambda p: (SECTIONS.index(p["section"]) if p["section"] in SECTIONS else 99, p["order"],
                                  p["title"]))
        _cache.update(stamp=stamp, items=items)
    return _cache["items"]


def allowed(page: dict, user) -> bool:
    from .auth import can_any
    needs = [n.strip() for n in page["needs"].split(",") if n.strip()]
    return not needs or can_any(user, needs)


def for_user(user) -> list[dict]:
    return [p for p in pages() if allowed(p, user)]


def get(slug: str, user) -> dict | None:
    return next((p for p in for_user(user) if p["slug"] == slug), None)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2]


def search(query: str, user, limit: int = 5) -> list[dict]:
    q = set(_words(query))
    if not q:
        return []
    scored = []
    for p in for_user(user):
        title = set(_words(p["title"]))
        body = _words(p["body"])
        score = 3 * len(q & title) + sum(1 for w in body if w in q) / max(1.0, len(body) ** 0.5)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:limit]]


def ask(question: str, user) -> dict:
    """Answer a question from the help pages with the local AI. Returns {answer, sources, error}."""
    from . import ai
    found = search(question, user, 3)
    if not found:
        return {"answer": "", "sources": [], "error": "No help page mentions that yet. Try other words."}
    context = "\n\n".join(f"### [{p['slug']}] {p['title']}\n{p['body'][:5000]}" for p in found)
    prompt = (f"You answer questions about NetGate, a web app, using ONLY the help pages below.\n"
              f"If the pages don't answer the question, say so in one sentence.\n"
              f"Write a short, plain answer (at most 6 sentences or a short list of steps).\n\n{context}\n\n"
              f"Question: {question}\n\n"
              f'Return JSON only: {{"answer": "...", "pages": ["slug of each page you used"]}}')
    try:
        data = ai.ask_json("help", prompt, timeout=120) or {}
    except Exception as e:
        return {"answer": "", "sources": found, "error": f"The AI could not be reached ({type(e).__name__}). "
                                                         "These help pages may answer it:"}
    used = [p for p in found if p["slug"] in (data.get("pages") or [])] or found
    return {"answer": str(data.get("answer") or "").strip(), "sources": used, "error": ""}


def changelog_html() -> str:
    for path in CHANGELOG:
        if os.path.exists(path):
            return markdown.markdown(open(path, encoding="utf-8").read(), extensions=["sane_lists"])
    return "<p>No changelog found.</p>"
