# Fake website for tests (needs the names dir.test jsdir.test acme.test beta.test -> 127.0.0.1 in /etc/hosts)
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
LIST1 = """<html><body><h1>Glove makers directory</h1><ul>
<li><a href="/company/acme">Acme Leather</a> — Sialkot, Pakistan</li>
<li><a href="/company/beta">Beta Gloves</a> — Sialkot, Pakistan</li>
<li><a href="/company/gamma">Gamma Sports</a> — Lahore, Pakistan</li>
</ul><p>Directory of glove manufacturers. Updated weekly with new suppliers and exporters from Pakistan.</p>
<a href="/list?page=2">Next »</a></body></html>"""
LIST2 = """<html><body><h1>Glove makers directory — page 2</h1><ul>
<li><a href="/company/delta">Delta Wear</a> — Sialkot, Pakistan</li>
<li><a href="https://epsilon.example/">Epsilon Leather Works</a> — Karachi, Pakistan</li>
<li>Zeta Apparel — Faisalabad, Pakistan</li></ul><p>More glove manufacturers and exporters, page two of the directory.</p></body></html>"""
PROFILES = {
 "acme": '<html><body><h1>Acme Leather</h1><p>Leather glove maker in Sialkot since 1990, exporting to Europe.</p><a href="http://acme.test/">Visit website</a><a href="tel:+92 52 1111111">Call</a><a href="mailto:info@acme.test">Email</a></body></html>',
 "beta": '<html><body><h1>Beta Gloves</h1><p>Motorcycle gloves. Contact: beta@gmail.com</p><a href="http://beta.test/">Website</a></body></html>',
 "delta": '<html><body><h1>Delta Wear</h1><p>Garments. Phone +92 52 2222222 for orders and samples.</p></body></html>',
}
JSTOP = """<html><body><div id="app"></div><script>window.x=1</script><script>
setTimeout(function(){document.getElementById('app').innerHTML='<h1>Top makers</h1><p>Theta Gear — Sialkot, Pakistan</p><p>Iota Moto — Lahore, Pakistan</p><p>Kappa Leathers — Sialkot, Pakistan</p><p>These manufacturers export motorcycle apparel worldwide.</p>';},200);
</script></body></html>"""
ACME_HOME = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme Leather",
"url":"http://acme.test/","address":{"@type":"PostalAddress","streetAddress":"12 Kashmir Road","addressLocality":"Sialkot","addressCountry":"PK"}}</script></head>
<body><h1>Acme Leather</h1><nav><a href="/">Home</a><a href="/contact">Contact us</a><a href="/blog/post-1">Blog</a><a href="/private/x">Private</a></nav>
<p>Welcome to Acme Leather, makers of leather motorcycle gloves and jackets in Sialkot.</p></body></html>"""
SITEMAP = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>http://acme.test/</loc></url><url><loc>http://acme.test/blog/post-1</loc></url>
<url><loc>http://acme.test/about-us</loc></url><url><loc>http://acme.test/impressum</loc></url></urlset>"""
PAGES = {
 ("dir.test", "/list"): LIST1, ("dir.test", "/list?page=1"): LIST1, ("dir.test", "/list?page=2"): LIST2,
 ("jsdir.test", "/top"): JSTOP,
 ("acme.test", "/"): ACME_HOME,
 ("acme.test", "/contact"): '<html><body><h1>Contact Acme Leather</h1><p>Write to sales@acme.test or info@acme.test.</p><a href="https://wa.me/923001112223">WhatsApp</a><a href="https://www.facebook.com/AcmeLeatherPK">Facebook</a><a href="https://www.facebook.com/sharer.php?u=x">Share</a> <p>Acme Leather contact page, Sialkot Pakistan, export office open Monday to Saturday.</p></body></html>',
 ("acme.test", "/about-us"): "<html><body><h1>About Acme Leather</h1><p>Acme Leather employs 120 workers making leather gloves and jackets for brands in Europe since 1990.</p></body></html>",
 ("acme.test", "/impressum"): "<html><body><h1>Impressum</h1><p>Acme Leather (Pvt) Ltd, 12 Kashmir Road, Sialkot. Tel +92 52 1111111.</p></body></html>",
 ("acme.test", "/blog/post-1"): "<html><body>Blog post about leather care.</body></html>",
 ("acme.test", "/sitemap.xml"): SITEMAP,
}
for k, v in PROFILES.items():
    PAGES[("dir.test", "/company/" + k)] = v
ROBOTS = {"dir.test": "User-agent: *\nDisallow: /company/gamma\n", "acme.test": "User-agent: *\nDisallow: /private\n"}
HITS = {}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        HITS[(host, self.path)] = HITS.get((host, self.path), 0) + 1
        if self.path == "/__hits":
            body, ctype, code = json.dumps({f"{h}{p}": n for (h, p), n in HITS.items()}), "application/json", 200
        elif self.path == "/robots.txt":
            body, ctype, code = ROBOTS.get(host, ""), "text/plain", 200 if host in ROBOTS else 404
        elif (host, self.path) in PAGES:
            body = PAGES[(host, self.path)]
            ctype = "application/xml" if self.path.endswith(".xml") else "text/html; charset=utf-8"
            code = 200
        else:
            body, ctype, code = "<html><body>Not found</body></html>", "text/html", 404
        data = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
ThreadingHTTPServer(("0.0.0.0", 80), H).serve_forever()
