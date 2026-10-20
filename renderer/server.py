"""NetGate page renderer: opens pages in headless Chromium.

GET  /render?url=https://...&wait=1500   ->  200 text/html after JavaScript ran (or 502 with an error message)
GET  /health                              ->  200 ok

v1.0 — search sessions for Browser search (one per search engine, cookies kept while the renderer runs):
POST /session/open?sid=bing&url=...      ->  JSON {url, html, title}
GET  /session/state?sid=bing             ->  JSON {url, html, title, open}
GET  /session/shot?sid=bing              ->  PNG screenshot of what the page shows now (for “Solve CAPTCHA Yourself”)
POST /session/click?sid=bing&x=..&y=..   ->  a person's click on the screenshot, passed to the page
POST /session/type?sid=bing&text=..      ->  typing;  POST /session/key?sid=bing&key=Enter  ->  one key
POST /session/close?sid=bing

Playwright may only be used from one thread, so every browser action runs on a single worker thread, one at a time
(it keeps memory low and is polite to websites); the web server answers on several threads so a screenshot can be
fetched while a search page is loading.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", 3000))
TIMEOUT_MS = int(os.environ.get("RENDER_TIMEOUT_MS", 25000))
MAX_BYTES = 3_000_000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
BLOCK = ("image", "media", "font")   # not needed to read text; makes pages much faster
VIEW = {"width": 1100, "height": 800}

ONE = ThreadPoolExecutor(max_workers=1)   # the only thread that touches Playwright
STATE: dict = {"pw": None, "browser": None, "sessions": {}}


def _browser():
    from playwright.sync_api import sync_playwright
    if STATE["pw"] is None:
        STATE["pw"] = sync_playwright().start()
    b = STATE["browser"]
    if b is None or not b.is_connected():
        STATE["browser"] = STATE["pw"].chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        STATE["sessions"] = {}
    return STATE["browser"]


def run(fn, *args):
    return ONE.submit(fn, *args).result(timeout=TIMEOUT_MS / 1000 + 30)


def _render(url: str, wait_ms: int) -> str:
    from playwright.sync_api import Error as PWError
    context = _browser().new_context(user_agent=UA + " NetGate/1.0", locale="en-GB", java_script_enabled=True)
    try:
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in BLOCK else route.continue_())
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=min(8000, TIMEOUT_MS))
        except PWError:
            pass  # busy pages never go fully idle; use what has loaded
        if wait_ms:
            page.wait_for_timeout(min(wait_ms, 5000))
        # scroll once so "load more on scroll" lists show their first extra batch
        page.evaluate("window.scrollTo(0, document.body ? document.body.scrollHeight : 0)")
        page.wait_for_timeout(500)
        return page.content()[:MAX_BYTES]
    finally:
        context.close()


# ---------- search sessions (v1.0) ----------

def _session(sid: str, create: bool = True):
    s = STATE["sessions"].get(sid)
    if s is None or s["page"].is_closed():
        if not create:
            return None
        ctx = _browser().new_context(user_agent=UA, locale="en-GB", viewport=VIEW)
        s = {"ctx": ctx, "page": ctx.new_page(), "at": time.time()}
        STATE["sessions"][sid] = s
    s["at"] = time.time()
    return s


def _snapshot(page) -> dict:
    try:
        html = page.content()[:MAX_BYTES]
    except Exception:  # noqa: BLE001 - the page is navigating
        page.wait_for_timeout(800)
        html = page.content()[:MAX_BYTES]
    return {"url": page.url, "html": html, "title": page.title(), "open": True}


def _open(sid: str, url: str) -> dict:
    from playwright.sync_api import Error as PWError
    page = _session(sid)["page"]
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except PWError:
        pass
    return _snapshot(page)


def _state(sid: str) -> dict:
    s = _session(sid, create=False)
    return _snapshot(s["page"]) if s else {"open": False, "url": "", "html": "", "title": ""}


def _shot(sid: str) -> bytes:
    s = _session(sid, create=False)
    return s["page"].screenshot(type="png") if s else b""


def _click(sid: str, x: float, y: float) -> dict:
    s = _session(sid, create=False)
    if not s:
        return {"open": False}
    s["page"].mouse.click(x, y)
    s["page"].wait_for_timeout(700)
    return {"open": True, "url": s["page"].url}


def _type(sid: str, text: str) -> dict:
    s = _session(sid, create=False)
    if not s:
        return {"open": False}
    s["page"].keyboard.type(text[:200], delay=40)
    return {"open": True}


def _key(sid: str, key: str) -> dict:
    s = _session(sid, create=False)
    if not s:
        return {"open": False}
    if key in ("Enter", "Tab", "Backspace", "Escape", "ArrowDown", "ArrowUp", "Space"):
        s["page"].keyboard.press(" " if key == "Space" else key)
        s["page"].wait_for_timeout(700)
    return {"open": True, "url": s["page"].url}


def _close(sid: str) -> dict:
    s = STATE["sessions"].pop(sid, None)
    if s:
        s["ctx"].close()
    return {"open": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    def _send(self, code: int, body, ctype: str = "text/plain; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj):
        return self._send(200, json.dumps(obj), "application/json")

    def _handle(self):
        parsed = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        path = parsed.path
        if path == "/health":
            return self._send(200, "ok")
        if path == "/render":
            url = q.get("url", "")
            if not url.startswith(("http://", "https://")):
                return self._send(400, "url must start with http:// or https://")
            try:
                wait = int(q.get("wait") or 0)
            except ValueError:
                wait = 0
            return self._send(200, run(_render, url, wait), "text/html; charset=utf-8")
        sid = (q.get("sid") or "")[:40]
        if path.startswith("/session/") and not sid:
            return self._send(400, "sid missing")
        if path == "/session/open":
            url = q.get("url", "")
            if not url.startswith(("http://", "https://")):
                return self._send(400, "url must start with http:// or https://")
            return self._json(run(_open, sid, url))
        if path == "/session/state":
            return self._json(run(_state, sid))
        if path == "/session/shot":
            png = run(_shot, sid)
            return self._send(200, png, "image/png") if png else self._send(404, "no such session")
        if path == "/session/click":
            return self._json(run(_click, sid, float(q.get("x") or 0), float(q.get("y") or 0)))
        if path == "/session/type":
            return self._json(run(_type, sid, q.get("text", "")))
        if path == "/session/key":
            return self._json(run(_key, sid, q.get("key", "")))
        if path == "/session/close":
            return self._json(run(_close, sid))
        return self._send(404, "not found")

    def _safe(self):
        try:
            self._handle()
        except Exception as e:  # report and keep serving
            b = STATE["browser"]
            if b is not None and not b.is_connected():
                STATE["browser"] = None
            try:
                self._send(502, f"{type(e).__name__}: {e}"[:500])
            except Exception:  # noqa: BLE001
                pass

    do_GET = _safe
    do_POST = _safe


if __name__ == "__main__":
    run(_browser)
    print(f"renderer listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
