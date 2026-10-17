---
title: eBay search
order: 36
updated: v0.7
---
**What it does:** finds business sellers on eBay marketplaces through the official Browse API, and fills seller details.

## How it works
- Keys: Settings → Connections (client id + secret; never shown back). Token: client credentials (`ebay._token`).
- `find_sellers()`: `item_summary/search` per marketplace with `sellerAccountTypes:{BUSINESS}` (if eBay answers 400, retried without and each seller checked), then `get_item` for `sellerLegalInfo` (business name, address, email, phone).
- Seller page link: `https://www.<host>/usr/<seller>`; the seller id is stored in `records.ext.ebay` (used for matching).
- Fields can be “Filled from” eBay values.

## Files
`app/ebay.py`, `app/methods.py` (`EBAY_DEFAULTS`), `tests/fake_ebay.py`.

## Settings
Per directory: marketplaces, category, results per keyword, minimum feedback, business only, max sellers. `EBAY_API_URL` env for tests.
