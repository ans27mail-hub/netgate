"""Learning from accept / reject decisions.

Every decision is saved (Decision table). New Inbox items are compared with contacts you accepted into
the same directory and with ones you rejected: the closest matches vote, which gives the "AI suggests …%"
shown in the Inbox. Nothing here trains a model; the decisions can be exported as training data for that.

Similarity uses a small word-hash vector by default (no extra software needed). If an embedding model is set
in Settings → AI servers (e.g. nomic-embed-text on the iMac), its vectors are used instead.
"""
import hashlib
import json
import re
from collections import Counter

import numpy as np
from sqlalchemy import select

from .db import Decision, Group, InboxItem, Membership, Record, SessionLocal, get_setting

DIM = 512
K = 15
MIN_EXAMPLES = 3
WORD = re.compile(r"[a-z0-9][a-z0-9&+.-]{1,30}", re.I)
STOP = {"the", "and", "for", "with", "from", "this", "that", "our", "your", "are", "www", "com", "http", "https",
        "ltd", "pvt", "limited", "company", "unknown", "none", "null"}


def text_of(rec) -> str:
    data = rec.data or {}
    parts = [rec.title or "", rec.summary or "", rec.domain or "", " ".join((rec.links or {}).keys())]
    for k, v in data.items():
        if isinstance(v, list):
            v = " ".join(map(str, v))
        parts.append(f"{k} {v}")
    return " ".join(parts)


def _tokens(text: str) -> list[str]:
    words = [w.lower().strip(".-") for w in WORD.findall(text or "")]
    words = [w for w in words if w and w not in STOP]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def hash_vector(text: str) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    for tok, n in Counter(_tokens(text)).items():
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
        v[h % DIM] += (1.0 + np.log(n)) * (1 if (h >> 31) & 1 else -1)
    norm = np.linalg.norm(v)
    return v / norm if norm else v


def embed_model(s) -> str:
    return str((get_setting(s, "learn", {}) or {}).get("embed_model") or "").strip()


def _embed(texts: list[str]) -> list[np.ndarray] | None:
    """Embeddings from the Discover AI server (Ollama). None when not set up or not reachable."""
    import httpx

    from . import ai
    with SessionLocal() as s:
        model = embed_model(s)
    if not model:
        return None
    try:
        server, _ = ai.pick("discover")
        if server.kind != "ollama":
            return None
        r = httpx.post(f"{server.url.rstrip('/')}/api/embed", json={"model": model, "input": texts}, timeout=120)
        r.raise_for_status()
        out = []
        for e in r.json().get("embeddings") or []:
            v = np.asarray(e, dtype=np.float32)
            n = np.linalg.norm(v)
            out.append(v / n if n else v)
        return out if len(out) == len(texts) else None
    except Exception:
        return None


def vectors(s, recs: list) -> np.ndarray:
    """One row per record. Uses stored embeddings when an embedding model is set, else word hashes."""
    if not recs:
        return np.zeros((0, DIM), dtype=np.float32)
    model = embed_model(s)
    if model:
        todo = [r for r in recs if r.vec is None or r.vec_model != model]
        for i in range(0, len(todo), 32):
            batch = todo[i:i + 32]
            embs = _embed([text_of(r)[:4000] for r in batch])
            if not embs:
                model = ""   # fall back to word hashes for this run
                break
            for r, v in zip(batch, embs):
                r.vec, r.vec_model = v.astype(np.float32).tobytes(), model
        if model:
            rows = [np.frombuffer(r.vec, dtype=np.float32) for r in recs]
            if len({len(x) for x in rows}) == 1:
                return np.vstack(rows)
    return np.vstack([hash_vector(text_of(r)) for r in recs])


def _examples(s, group_id: int | None, limit: int = 3000):
    """(records, labels, reasons) the user decided on for this directory: 1 = accepted, 0 = rejected."""
    if group_id:
        pos_ids = s.scalars(select(Membership.record_id).where(Membership.group_id == group_id)
                            .order_by(Membership.added_at.desc()).limit(limit)).all()
        neg = s.execute(select(InboxItem.record_id, InboxItem.reason).where(
            InboxItem.group_id == group_id, InboxItem.status == "rejected")
            .order_by(InboxItem.decided_at.desc()).limit(limit)).all()
    else:
        pos_ids = s.scalars(select(Membership.record_id).order_by(Membership.added_at.desc()).limit(limit)).all()
        neg = s.execute(select(InboxItem.record_id, InboxItem.reason).where(InboxItem.status == "rejected")
                        .order_by(InboxItem.decided_at.desc()).limit(limit)).all()
    ids = list(dict.fromkeys(list(pos_ids) + [r for r, _ in neg]))
    recs = {r.id: r for r in s.scalars(select(Record).where(Record.id.in_(ids or [-1]))).all()}
    rows, labels, reasons = [], [], []
    for rid in pos_ids:
        if rid in recs:
            rows.append(recs[rid]); labels.append(1); reasons.append("")
    pos_set = set(pos_ids)
    for rid, reason in neg:
        if rid in recs and rid not in pos_set:
            rows.append(recs[rid]); labels.append(0); reasons.append(reason or "")
    return rows, np.asarray(labels, dtype=np.float32), reasons


def score_items(s, items: list[InboxItem]):
    """Fill item.suggest / score / why for Inbox items (grouped by directory)."""
    by_group: dict = {}
    for it in items:
        by_group.setdefault(it.group_id, []).append(it)
    for gid, its in by_group.items():
        rows, labels, reasons = _examples(s, gid)
        recs = [s.get(Record, it.record_id) for it in its]
        if len(rows) < MIN_EXAMPLES:
            for it in its:
                if it.method in ("manual", "csv"):
                    it.suggest, it.score, it.why = "accept", None, "directory chosen when added"
                else:
                    it.suggest, it.score, it.why = None, None, "not enough decisions yet"
            continue
        ex = vectors(s, rows)
        q = vectors(s, [r for r in recs if r])
        sims = q @ ex.T
        for i, it in enumerate([it for it, r in zip(its, recs) if r]):
            top = np.argsort(-sims[i])[:K]
            w = np.clip(sims[i][top], 0, None) + 1e-6
            p = float((w * labels[top]).sum() / w.sum())
            strength = float(np.mean(np.clip(sims[i][top[:5]], 0, None)))
            close = [j for j in top if sims[i][j] >= 0.25]
            if strength < 0.08:
                it.suggest, it.score, it.why = None, None, "not like anything decided yet"
                continue
            if p >= 0.5:
                n = sum(1 for j in close if labels[j] == 1)
                it.suggest, it.score = "accept", p
                it.why = f"like {n} you accepted" if n else "closest to ones you accepted"
            else:
                rs = Counter(reasons[j] for j in close if labels[j] == 0 and reasons[j])
                n = sum(1 for j in close if labels[j] == 0)
                it.suggest, it.score = "reject", 1 - p
                top_reason = rs.most_common(1)[0][0].lower() if rs else ""
                it.why = (f"like {n} you rejected" + (f" as {top_reason}" if top_reason else "")) if n \
                    else "closest to ones you rejected"
            it.score = round(it.score, 3)


def rescore_group(group_id: int | None):
    """Background task after decisions: refresh suggestions of the open items of a directory."""
    with SessionLocal() as s:
        stmt = select(InboxItem).where(InboxItem.status == "new")
        stmt = stmt.where(InboxItem.group_id == group_id) if group_id else stmt.where(InboxItem.group_id.is_(None))
        items = s.scalars(stmt.order_by(InboxItem.created_at.desc()).limit(500)).all()
        score_items(s, items)
        s.commit()


# ---------- training data ----------

def training_rows(s, limit: int = 20000):
    """Decisions as chat-style examples (JSONL), for fine-tuning a model later."""
    groups = {g.id: g for g in s.scalars(select(Group)).all()}
    for d in s.scalars(select(Decision).where(Decision.decision.in_(["accept", "reject"]))
                       .order_by(Decision.id).limit(limit)).all():
        g = groups.get(d.group_id)
        system = (f"You sort companies into the \"{g.name if g else 'directory'}\" directory. "
                  f"What belongs: {(g.instructions if g else '') or '-'} Skip: {(g.ignore_instructions if g else '') or '-'}")
        user = json.dumps(d.snapshot or {}, ensure_ascii=False)
        answer = {"decision": d.decision}
        if d.reason:
            answer["reason"] = d.reason
        yield {"messages": [{"role": "system", "content": system},
                            {"role": "user", "content": f"Found by {d.method or 'search'} \"{d.keyword}\":\n{user}"},
                            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}],
               "meta": {"at": d.at.isoformat() if d.at else "", "directory": g.name if g else "",
                        "user_id": d.user_id}}
