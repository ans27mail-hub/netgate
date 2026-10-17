---
title: Tags
order: 70
updated: v0.7
---
**What it does:** labels like *Hot lead*, *Sample sent*, *Customer* with a colour. A contact can have several; the tag highest in the order colours the card.

## How it works
- Tables `tags` (name, colour, description, position, `color_card`, `all_groups` / `group_ids`) and `record_tags`.
- `app/tags.py`: `tags_map()` (tags per contact, strongest first), `tint()` (card background / border mixed from the tag colour), `set_tags` / `add_tag` / `remove_tag` (history lines), `usable_in()` (tags limited to some directories).
- Settings → Tags (`look_routes`): new, edit (name, meaning, 10 colours or own hex, where it can be used, colour the card), order ↑ ↓, merge into another, delete (only takes it off contacts).
- On cards: small rounded bars beside the Enrich button (style A/B/C); hover = name, click = filter `?tag=<id>`. Tag bar above the cards with counts. Filter chip “Tag”. Sort “Tag Order”. List view: column “Tags”, bulk **Add Tag** / **Remove Tag**.
- Six starting tags are added once by `_upgrade_v07`.

## Permissions
*Manage tags* for Settings → Tags; *Edit contacts* to put tags on contacts.

## Files
`app/tags.py`, `app/web/look_routes.py`, `templates/tags.html`, `contacts.html`, `_bigcard.html`.
