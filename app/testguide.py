"""Testing Guide (v1.0): step-by-step checklists a person follows to test NetGate in the browser.

Checklists are Markdown files in app/testguide/<slug>.md (code, added with each version — never edited in the UI):

    ---
    title: Keyword Library
    feature: keyword-library        (the Developer Handbook feature it tests)
    order: 40
    ---
    Short intro.

    1. (v1.0) Open Keywords in the menu. => The library opens with the starter categories.
    2. Add the word "gloves". => It appears in the list.

Each numbered line is one step: what to do, then “=>” and what you should see. “(v1.0)” marks a step added in
that version, so a run can test “only what is new”. A test checks that every Handbook feature has a checklist and
that the current version added at least one step.

Runs are saved per version (TestRun: results {step id: {ok, note, by, at}}); screenshots in TestShot.
"""
import os
import re
from datetime import datetime

ROOT = os.path.join(os.path.dirname(__file__), "testguide")
STEP = re.compile(r"^\s*(\d+)\.\s+(?:\((v\d+\.\d+)\)\s*)?(.+)$")
RESULTS = {"pass": "Passed", "fail": "Failed", "skip": "Skipped"}


def _parse(path: str, slug: str) -> dict:
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    intro, steps = [], []
    for line in body.splitlines():
        sm = STEP.match(line)
        if sm:
            text = sm.group(3).strip()
            do, _, expect = text.partition("=>")
            steps.append({"id": f"{slug}:{sm.group(1)}", "n": int(sm.group(1)), "since": sm.group(2) or "",
                          "do": do.strip(), "expect": expect.strip()})
        elif line.strip() and not steps:
            intro.append(line.strip())
    return {"slug": slug, "title": meta.get("title") or slug, "feature": meta.get("feature") or slug,
            "order": int(meta.get("order") or 50), "intro": " ".join(intro), "steps": steps}


def checklists() -> list[dict]:
    if not os.path.isdir(ROOT):
        return []
    out = [_parse(os.path.join(ROOT, f), f[:-3]) for f in sorted(os.listdir(ROOT)) if f.endswith(".md")]
    return sorted(out, key=lambda c: (c["order"], c["title"]))


def for_scope(scope: str, version: str) -> list[dict]:
    """The checklists of a run: everything, or only the steps added in `version`."""
    out = []
    for c in checklists():
        steps = c["steps"] if scope != "new" else [st for st in c["steps"] if st["since"] == version]
        if steps:
            out.append({**c, "steps": steps})
    return out


def counts(run, lists=None) -> dict:
    lists = lists if lists is not None else for_scope(run.scope, run.version)
    ids = [st["id"] for c in lists for st in c["steps"]]
    res = run.results or {}
    n = {k: sum(1 for i in ids if (res.get(i) or {}).get("ok") == k) for k in RESULTS}
    n["total"], n["todo"] = len(ids), len(ids) - sum(n[k] for k in RESULTS)
    return n


def report(run, lists, names: dict) -> str:
    """Plain text of the failed steps (with notes), to copy into a message for the developer."""
    res = run.results or {}
    lines = [f"NetGate {run.version} test run #{run.id} by {names.get(run.user_id, '?')}"
             f" ({run.started_at:%d %b %Y}) — failed steps:"]
    for c in lists:
        for st in c["steps"]:
            r = res.get(st["id"]) or {}
            if r.get("ok") == "fail":
                lines.append(f"- {c['title']} step {st['n']}: {st['do']}"
                             + (f"\n  Expected: {st['expect']}" if st["expect"] else "")
                             + (f"\n  Note: {r['note']}" if r.get("note") else ""))
    if len(lines) == 1:
        lines.append("(none)")
    return "\n".join(lines)


def set_result(run, step_id: str, ok: str, note: str, by: str):
    res = dict(run.results or {})
    if ok not in RESULTS and not note:
        res.pop(step_id, None)
    else:
        res[step_id] = {"ok": ok if ok in RESULTS else "", "note": note[:1000], "by": by,
                        "at": datetime.utcnow().isoformat(timespec="seconds")}
    run.results = res
