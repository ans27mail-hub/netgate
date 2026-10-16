"""NetGate page renderer: opens a page in headless Chromium and returns the HTML after JavaScript has run.

GET /render?url=https://...&wait=1500   ->  200 text/html  (or 502 with an error message)
GET /health                              ->  200 ok

Requests are handled one at a time on purpose: it keeps memory low and is polite to websites.
"""
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PWError
from playwright.sync_api import sync_playwright

PORT = int(os.environ.get("PORT", 3000))
TIMEOUT_MS = int(os.environ.get("RENDER_TIMEOUT_MS", 25000))
MAX_BYTES = 3_000_000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36 NetGate/0.4")
BLOCK = ("image", "media", "font")   # not needed to read text; makes pages much faster

pw = sync_playwright().start()
browser = None


def get_browser():
    global browser
    if browser is None or not browser.is_connected():
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    return browser


def render(url: str, wait_ms: int) -> str:
    context = get_browser().new_context(user_agent=UA, locale="en-GB", java_script_enabled=True)
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    def _send(self, code: int, body: str, ctype: str = "text/plain; charset=utf-8"):
        data = body.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send(200, "ok")
        if parsed.path != "/render":
            return self._send(404, "not found")
        q = parse_qs(parsed.query)
        url = (q.get("url") or [""])[0]
        if not url.startswith(("http://", "https://")):
            return self._send(400, "url must start with http:// or https://")
        try:
            wait = int((q.get("wait") or ["0"])[0])
        except ValueError:
            wait = 0
        try:
            html = render(url, wait)
        except Exception as e:  # report and keep serving
            global browser
            if browser is not None and not browser.is_connected():
                browser = None
            return self._send(502, f"{type(e).__name__}: {e}"[:500])
        return self._send(200, html, "text/html; charset=utf-8")


if __name__ == "__main__":
    get_browser()
    print(f"renderer listening on :{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
