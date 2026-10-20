"""Search methods a directory can use. Each method knows how its site works.

New methods (or "recipes" for a particular site) are added in code through GitHub, never in the web page.
"""

METHODS = {
    # key: name, step (find / enrich), tag, description, ready
    "web": {"name": "Web search", "step": "find", "tag": "Crawler", "kind": "web", "ready": True,
            "desc": "General search engine results; list and company pages are read by code and the AI."},
    "directory": {"name": "Directory site search", "step": "find", "tag": "Crawler", "kind": "web", "ready": True,
                  "desc": "Reads B2B directory list pages, their next pages and each company's profile."},
    "browser": {"name": "Browser search", "step": "find", "tag": "Browser", "kind": "web", "ready": True,
                "desc": "NetGate's own browser searches Bing / DuckDuckGo like a person and reads the results until "
                        "enough new companies are found. A CAPTCHA can be solved by you."},
    "ebay": {"name": "eBay search", "step": "find", "tag": "Official API", "kind": "api", "ready": True,
             "desc": "Finds sellers from eBay listings, then reads each seller's details."},
    "etsy": {"name": "Etsy search", "step": "find", "tag": "Official API · later", "kind": "api", "ready": False,
             "desc": "Finds Etsy shops selling matching items. Comes in a later version."},
    "amazon": {"name": "Amazon search", "step": "find", "tag": "Limited · later", "kind": "limited", "ready": False,
               "desc": "Finds Amazon sellers through search-engine results. Comes in a later version."},
    "website": {"name": "Company website (Enrich)", "step": "enrich", "tag": "Crawler", "kind": "web", "ready": True,
                "desc": "Reads each company's own site: Contact, About, Impressum and the sitemap."},
    "recipe": {"name": "Custom recipe", "step": "find", "tag": "Via GitHub · later", "kind": "custom",
               "ready": False, "desc": "A site of your own choice with its own reading rules, added through an update."},
}
FIND_METHODS = [k for k, m in METHODS.items() if m["step"] == "find" and m["ready"]]

EBAY_DEFAULTS = {"sites": [], "category_id": "", "per_keyword": 200, "min_feedback": 0, "business_only": True,
                 "max_sellers": 60}
DIRECTORY_DEFAULTS = {"start_urls": "", "sites": ""}
BROWSER_DEFAULTS = {"want": 20, "max_pages": 5, "max_minutes": 15, "engines": []}   # [] = Settings → Search Engines

# "Filled from" choices for a field. '' = the usual way: code first, then the AI, from pages read.
FIELD_SOURCES = [
    ("", "AI + code (from pages read)"),
    ("website", "Company website only"),
    ("manual", "Manual only (never searched)"),
    ("method:marketplace", "Method: marketplace name (eBay …)"),
    ("ebay:username", "eBay: seller name"),
    ("ebay:business_name", "eBay: business name"),
    ("ebay:feedback_pct", "eBay: positive feedback %"),
    ("ebay:feedback_score", "eBay: feedback score"),
    ("ebay:country", "eBay: item location (country)"),
    ("ebay:city", "eBay: item location (city)"),
    ("ebay:address", "eBay: business address"),
    ("ebay:email", "eBay: business email"),
    ("ebay:phone", "eBay: business phone"),
    ("ebay:vat", "eBay: VAT number"),
    ("ebay:store_url", "eBay: seller page"),
    ("ebay:products", "eBay: listing titles"),
    ("ebay:sites", "eBay: marketplaces"),
]
SOURCE_LABELS = dict(FIELD_SOURCES)

# Steps of Enrich, in order. "Add contact" lets the user pick them.
ENRICH_STEPS = [
    ("ebay", "eBay store lookup", "Reads the eBay seller from its link or name: rating, feedback, location, business details.", "Official API"),
    ("find_site", "Find own website", "Searches the name + city / country to find the company's own website.", "Crawler"),
    ("website", "Company website", "Reads the website's Contact, About and sitemap pages for email, phone, address, products.", "Crawler"),
    ("social", "Social links", "Finds Facebook, Instagram and LinkedIn pages from search results.", "Crawler"),
    ("web", "Other pages", "Reads other pages that mention the company, and search-result snippets.", "Crawler"),
]
ENRICH_STEP_KEYS = [k for k, *_ in ENRICH_STEPS]


def enabled_find_methods(group) -> list[str]:
    return [k for k in FIND_METHODS if k in (group.methods or {})] or ["web"]


def options(group, key: str) -> dict:
    defaults = {"ebay": EBAY_DEFAULTS, "directory": DIRECTORY_DEFAULTS, "browser": BROWSER_DEFAULTS}.get(key, {})
    return {**defaults, **((group.methods or {}).get(key) or {})}


def keyword_methods(group, keyword) -> list[str]:
    """Which find methods a keyword runs with."""
    enabled = enabled_find_methods(group)
    m = getattr(keyword, "method", "all") or "all"
    return enabled if m == "all" else [m] if m in enabled else enabled


def suggested_source(field_key: str, methods: dict) -> str:
    """When a directory uses eBay, some common fields are filled from it."""
    if "ebay" not in (methods or {}):
        return ""
    return {"seller_rating": "ebay:feedback_pct", "feedback_count": "ebay:feedback_score",
            "sells_on": "method:marketplace", "business_name": "ebay:business_name"}.get(field_key, "")


CONNECTION_DEFAULTS = {
    "ebay": {"client_id": "", "client_secret": "", "sites": ["EBAY_GB", "EBAY_DE", "EBAY_IT", "EBAY_FR",
                                                              "EBAY_US", "EBAY_CA"], "business_only": True},
    "etsy": {"api_key": "", "shared_secret": ""},
}


def connections(s) -> dict:
    from .db import get_setting
    saved = get_setting(s, "connections", {}) or {}
    return {k: {**v, **(saved.get(k) or {})} for k, v in CONNECTION_DEFAULTS.items()}
