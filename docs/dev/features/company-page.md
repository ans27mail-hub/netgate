---
title: Company page, Verify, profile and products
order: 43
updated: v1.0
---
**What it does:** `/companies/{id}` shows everything about one company: each detail with how it was found (read from a page, typed in, eBay, CSV), the page link, when it was found and last checked; Verify; a short profile made by the local AI from the website; products (from the website or added by hand); pages read; history.

## How it works
- Found dates: `contacts.stamp(record, keys, checked=False)` writes `records.meta[key] = {at, checked, verify}`; called by `contacts.upsert`, Enrich (new value → `at`; same value on Check All Again → `checked`) and Edit.
- `app/verify.py`:
  - `verify(ctx, record_id, keys)`: groups values by their source page, reads each page **without the cache**, checks by code (`on_page`: digits for phones, case-insensitive text) → `same`; otherwise code (`extract.fill_fields`) then the AI for that one field → `changed` with `new`, else `not_found`; unreadable page → `gone`. Saves `meta[key]["verify"]` and `meta["_verified"]`. Nothing changes until a person clicks Accept New Value / Keep Old (or Remove It for not found).
  - `profile(ctx, record_id)`: reads the home page and up to 3 product/about pages (purpose `company`), asks the AI for type, summary, categories (only from Settings → Product Categories), main products, materials, markets, certifications, founded, products (≤30); finds a picture link by `<img alt>`; replaces NetGate's own products, keeps hand-added ones.
- Job kinds `verify` and `profile` (AI type *enrich*), started from the Company page (permission like Enrich).
- Night Jobs: `verify_months` (0 = off) and `verify_max` — step 4 of the night run verifies contacts not checked for that long.
- `app/web/company_routes.py`: page, `POST /companies/{id}/verify|profile|accept|keep|product-add|product-delete`, `/settings/product-categories` (permission Manage directories).

## Data
`records.meta` JSON, `records.profile` JSON, `products` (record_id, name, category, image_url, source_url, price, moq, added_by, created_at). Product categories in `app_settings["product_categories"]` (default list in `verify.DEFAULT_CATEGORIES`). Pages read purposes `verify` and `company`.

## Tests
`test_v10.py` (found dates, verify same/changed/not found/gone, accept/keep, profile and products, categories, night verify).

## Limits & ideas
Pictures are only links to the company's site (nothing is downloaded). Verify checks values that came from a page; typed-in values are shown as “Not from a page”.
