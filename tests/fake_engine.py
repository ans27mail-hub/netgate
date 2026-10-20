"""A fake search engine for Browser search tests (port 3996). Run with BROWSER_ENGINE_URLS pointing at it:
  {"bing": "http://127.0.0.1:3996/bing?q={q}&first={first}", "duckduckgo": "http://127.0.0.1:3996/ddg?q={q}&s={first0}"}
/bing returns Bing-like results (li.b_algo h2 a) linking to dir.test/list and jsdir.test/top on page 1.
/__captcha?on=1 makes it answer with a CAPTCHA page until a person clicks anywhere on it (sets a cookie);
/__captcha?on=0 switches that off. /__calls lists the searches.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MODE = {"captcha": False}
CALLS = []
RESULTS = """<html><head><title>{q} - Search</title></head><body><ol id="b_results">
<li class="b_algo"><h2><a href="http://dir.test/list">Glove makers directory</a></h2><p>Glove makers</p></li>
<li class="b_algo"><h2><a href="http://jsdir.test/top">Top makers</a></h2><p>Top makers</p></li>
<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?x=1">Ad</a></h2></li>
</ol></body></html>"""
EMPTY = "<html><body><ol id='b_results'></ol><p>There are no results.</p></body></html>"
DDG = """<html><body><div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=http%3A%2F%2Fdir.test%2Flist">Dir</a></div></body></html>"""
CAPTCHA = """<html><head><title>Verify</title></head><body style="margin:0">
<form method="post" action="/__solve?back={back}" style="margin:0">
<button type="submit" style="width:100vw;height:100vh;font-size:40px">One last step: please solve this CAPTCHA — click to prove you are not a robot</button>
</form></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/__solve":
            back = parse_qs(u.query).get("back", ["/bing"])[0]
            return self._send(303, "", headers={"Set-Cookie": "solved=1; Path=/", "Location": back})
        return self._send(404, "")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/__captcha":
            MODE["captcha"] = q.get("on") == "1"
            return self._send(200, json.dumps(MODE), "application/json")
        if u.path == "/__calls":
            return self._send(200, json.dumps(CALLS), "application/json")
        if u.path == "/__reset":
            CALLS.clear()
            return self._send(200, "[]", "application/json")
        if u.path in ("/bing", "/ddg"):
            CALLS.append({"path": u.path, "q": q.get("q", ""), "first": q.get("first") or q.get("s")})
            solved = "solved=1" in (self.headers.get("Cookie") or "")
            if MODE["captcha"] and not solved:
                from urllib.parse import quote
                return self._send(200, CAPTCHA.replace("{back}", quote(self.path, safe="")))
            if u.path == "/ddg":
                return self._send(200, DDG)
            first = int(q.get("first") or 1)
            return self._send(200, RESULTS.replace("{q}", q.get("q", "")) if first == 1 else EMPTY)
        return self._send(404, "not found")


ThreadingHTTPServer(("127.0.0.1", 3996), H).serve_forever()
