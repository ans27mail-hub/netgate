"""A fake SearXNG for tests/test_v08.py (port 3997): /search (JSON), /config, /healthz.

Engines: google, bing, duckduckgo (on by default), brave, mojeek (off by default), wikipedia (on).
/__block?google=CAPTCHA makes google fail (listed in unresponsive_engines); /__block clears it.
/__calls lists the searches received (q, pageno, engines); /__reset clears them.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ENGINES = [("google", True), ("bing", True), ("duckduckgo", True), ("brave", False), ("mojeek", False),
           ("wikipedia", True)]
DEFAULT = [n for n, on in ENGINES if on]
BLOCK: dict = {}
CALLS: list = []

# which engine gives which link (first result page of a glove search)
LINKS = {
    "google": ["http://dir.test/list"],
    "bing": ["http://dir.test/list", "http://jsdir.test/top"],
    "duckduckgo": ["http://jsdir.test/top"],
    "brave": ["http://dir.test/list"],
    "mojeek": ["http://jsdir.test/top"],
    "wikipedia": [],
}


def results_for(q: str, pageno: int, engines: list[str]):
    out: dict = {}
    if "nothing" in q.lower():
        return []
    for e in engines:
        if e in BLOCK:
            continue
        links = LINKS.get(e, []) if pageno == 1 else ([f"http://dir.test/list?page={pageno}"] if e == "bing" else [])
        for u in links:
            out.setdefault(u, []).append(e)
    return [{"url": u, "title": u, "content": "", "engine": engs[0], "engines": engs} for u, engs in out.items()]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/healthz":
            return self._send(200, "OK")
        if u.path == "/config":
            return self._send(200, {"engines": [{"name": n, "categories": ["general", "web"], "enabled": on}
                                                for n, on in ENGINES]})
        if u.path == "/__block":
            BLOCK.clear()
            BLOCK.update(qs)
            return self._send(200, BLOCK)
        if u.path == "/__calls":
            return self._send(200, CALLS)
        if u.path == "/__reset":
            CALLS.clear()
            return self._send(200, [])
        if u.path == "/search":
            engines = [e for e in (qs.get("engines") or "").split(",") if e] or DEFAULT
            pageno = int(qs.get("pageno") or 1)
            CALLS.append({"q": qs.get("q", ""), "pageno": pageno, "engines": qs.get("engines")})
            res = results_for(qs.get("q", ""), pageno, engines)
            return self._send(200, {"query": qs.get("q"), "results": res,
                                    "unresponsive_engines": [[e, BLOCK[e]] for e in engines if e in BLOCK]})
        return self._send(404, {})


ThreadingHTTPServer(("127.0.0.1", 3997), H).serve_forever()
