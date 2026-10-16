"""Fake eBay Browse API for tests."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote
CALLS = []
ITEMS = {
  "EBAY_GB": [
    {"itemId": "v1|1|0", "title": "Leather motorcycle jacket black", "seller": {"username": "rider_store_uk", "feedbackPercentage": "99.2", "feedbackScore": 4210}, "itemLocation": {"country": "GB", "city": "Leeds"}},
    {"itemId": "v1|2|0", "title": "Leather motorcycle jacket brown", "seller": {"username": "rider_store_uk", "feedbackPercentage": "99.2", "feedbackScore": 4210}, "itemLocation": {"country": "GB"}},
    {"itemId": "v1|3|0", "title": "Vintage biker jacket", "seller": {"username": "joe_private", "feedbackPercentage": "100", "feedbackScore": 12}, "itemLocation": {"country": "GB"}},
    {"itemId": "v1|4|0", "title": "Motorbike leather jacket CE armour", "seller": {"username": "moto_gear_direct", "feedbackPercentage": "98.7", "feedbackScore": 12000}, "itemLocation": {"country": "GB", "city": "Manchester"}},
  ],
  "EBAY_DE": [
    {"itemId": "v1|9|0", "title": "Motorrad Lederjacke", "seller": {"username": "motoshop_de", "feedbackPercentage": "99.6", "feedbackScore": 18900}, "itemLocation": {"country": "DE"}},
  ],
}
DETAIL = {
  "v1|1|0": {"sellerAccountType": "BUSINESS", "sellerLegalInfo": {"name": "Rider Store Ltd", "email": "sales@riderstore.co.uk", "phone": "+44 113 555 0101", "sellerProvidedLegalAddress": {"addressLine1": "1 Mill Street", "city": "Leeds", "postalCode": "LS1 1AA", "country": "GB", "countryName": "United Kingdom"}, "vatDetails": [{"issuingCountry": "GB", "vatId": "GB123456789"}]}},
  "v1|3|0": {"sellerAccountType": "INDIVIDUAL"},
  "v1|4|0": {"sellerAccountType": "BUSINESS", "sellerLegalInfo": {"name": "Moto Gear Direct", "email": "info@motogeardirect.com", "sellerProvidedLegalAddress": {"city": "Manchester", "country": "GB"}}},
  "v1|9|0": {"sellerAccountType": "BUSINESS", "sellerLegalInfo": {"name": "Motoshop GmbH", "phone": "+49 30 1234567", "sellerProvidedLegalAddress": {"city": "Berlin", "country": "DE"}}},
}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        CALLS.append(("POST", self.path))
        n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
        if self.path.startswith("/identity/v1/oauth2/token"):
            if "Basic" not in (self.headers.get("Authorization") or ""):
                return self._send(401, {"error": "invalid_client"})
            return self._send(200, {"access_token": "TOKEN", "expires_in": 7200})
        self._send(404, {})
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        CALLS.append(("GET", self.path, self.headers.get("X-EBAY-C-MARKETPLACE-ID")))
        if u.path == "/__calls":
            return self._send(200, CALLS)
        if self.headers.get("Authorization") != "Bearer TOKEN":
            return self._send(401, {})
        site = self.headers.get("X-EBAY-C-MARKETPLACE-ID")
        if u.path == "/buy/browse/v1/item_summary/search":
            flt = (q.get("filter") or [""])[0]
            if "sellerAccountTypes" in flt and site == "EBAY_DE":
                return self._send(400, {"errors": [{"message": "filter not supported"}]})
            items = list(ITEMS.get(site, []))
            if "sellers:{" in flt:
                who = flt.split("sellers:{")[1].split("}")[0]
                items = [i for i in items if i["seller"]["username"] == who]
            off = int((q.get("offset") or ["0"])[0]); lim = int((q.get("limit") or ["50"])[0])
            return self._send(200, {"total": len(items), "itemSummaries": items[off:off + lim]})
        if u.path.startswith("/buy/browse/v1/item/"):
            iid = unquote(u.path.rsplit("/", 1)[1])
            base = next((i for s in ITEMS.values() for i in s if i["itemId"] == iid), None)
            if not base:
                return self._send(404, {})
            d = dict(base); seller = dict(base["seller"]); seller.update(DETAIL.get(iid, {})); d["seller"] = seller
            return self._send(200, d)
        self._send(404, {})
ThreadingHTTPServer(("0.0.0.0", 3998), H).serve_forever()
