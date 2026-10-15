"""Talk to the AI: Ollama servers (iMac, GPU PC) or OpenRouter, chosen per job type in Settings."""
import json
import re
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select

from .db import AIServer, AIUsage, SessionLocal, get_setting

OPENROUTER_URL = "https://openrouter.ai/api/v1"
JOB_TYPES = {"discover": "Discover", "enrich": "Enrich", "night": "Night jobs"}


class AIError(Exception):
    pass


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            value = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def spent(s, since: datetime) -> float:
    return float(s.scalar(select(func.coalesce(func.sum(AIUsage.cost), 0.0)).where(AIUsage.at >= since)) or 0.0)


def over_budget(s) -> bool:
    limits = get_setting(s, "ai.limits", {}) or {}
    now = datetime.utcnow()
    day_limit = float(limits.get("night") or 0)
    month_limit = float(limits.get("month") or 0)
    if day_limit and spent(s, now - timedelta(hours=24)) >= day_limit:
        return True
    if month_limit and spent(s, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)) >= month_limit:
        return True
    return False


def pick(job_type: str):
    """Return (server, model) for a job type, falling back when OpenRouter is over budget or off."""
    with SessionLocal() as s:
        conf = get_setting(s, f"ai.{job_type}") or get_setting(s, "ai.discover") or {}
        server = s.get(AIServer, conf.get("server")) if conf.get("server") else None
        model = conf.get("model") or ""
        if server and server.kind == "openrouter" and (not server.enabled or not server.api_key or over_budget(s)):
            server = None
        if not server or not server.enabled:
            fb = get_setting(s, "ai.fallback") or {}
            server = s.get(AIServer, fb.get("server")) if fb.get("server") else None
            model = fb.get("model") or model
        if not server:
            server = s.scalar(select(AIServer).where(AIServer.enabled, AIServer.kind == "ollama").order_by(AIServer.id))
        if not server:
            raise AIError("No AI server is set up. Add one in Settings → AI servers.")
        return server, model


def _ollama(server, model: str, prompt: str, timeout: int) -> str:
    body = {"model": model, "prompt": prompt, "format": "json", "stream": False, "think": False,
            "options": {"temperature": 0.1, "num_ctx": 8192}}
    r = httpx.post(f"{server.url.rstrip('/')}/api/generate", json=body, timeout=timeout)
    if r.status_code == 400 and "think" in r.text:
        body.pop("think")  # model without a thinking mode
        r = httpx.post(f"{server.url.rstrip('/')}/api/generate", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "")


def _openrouter(server, model: str, prompt: str, timeout: int, job_type: str) -> str:
    r = httpx.post(f"{OPENROUTER_URL}/chat/completions", timeout=timeout,
                   headers={"Authorization": f"Bearer {server.api_key}", "X-Title": "NetGate"},
                   json={"model": model, "messages": [{"role": "user", "content": prompt}],
                         "response_format": {"type": "json_object"}, "temperature": 0.1,
                         "usage": {"include": True}})
    r.raise_for_status()
    data = r.json()
    cost = float((data.get("usage") or {}).get("cost") or 0.0)
    with SessionLocal() as s:
        s.add(AIUsage(server_id=server.id, job_type=job_type, model=model, cost=cost))
        s.commit()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")


def ask_json(job_type: str, prompt: str, timeout: int = 300) -> dict | None:
    server, model = pick(job_type)
    if server.kind == "openrouter":
        text = _openrouter(server, model, prompt, timeout, job_type)
    else:
        text = _ollama(server, model, prompt, timeout)
    return _parse_json(text)


def list_models(server, timeout: float = 4.0) -> list[dict]:
    """[{'id': 'qwen3:8b', 'price': None}] — prices (USD per million input tokens) only for OpenRouter."""
    try:
        if server.kind == "openrouter":
            r = httpx.get(f"{OPENROUTER_URL}/models", timeout=timeout)
            r.raise_for_status()
            out = []
            for m in r.json().get("data", []):
                p = (m.get("pricing") or {}).get("prompt")
                out.append({"id": m["id"], "price": round(float(p) * 1_000_000, 3) if p not in (None, "") else None})
            return sorted(out, key=lambda m: m["id"])
        r = httpx.get(f"{server.url.rstrip('/')}/api/tags", timeout=timeout)
        r.raise_for_status()
        return sorted(({"id": m["name"], "price": None} for m in r.json().get("models", [])), key=lambda m: m["id"])
    except (httpx.HTTPError, KeyError, ValueError):
        return []


def test_server(server, model: str) -> tuple[bool, str]:
    try:
        started = datetime.utcnow()
        if server.kind == "openrouter":
            if not server.api_key:
                return False, "No API key set."
            text = _openrouter(server, model, 'Reply with JSON: {"ok": true}', 60, "test")
        else:
            text = _ollama(server, model, 'Reply with JSON: {"ok": true}', 120)
        secs = (datetime.utcnow() - started).total_seconds()
        ok = bool((_parse_json(text) or {}).get("ok"))
        return ok, (f"{model} answered in {secs:.1f} s." if ok else f"{model} answered, but not with the expected JSON.")
    except httpx.HTTPError as e:
        return False, f"Could not reach {server.name}: {type(e).__name__}"
