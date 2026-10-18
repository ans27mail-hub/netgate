---
title: Card styles and short-card fields
order: 75
updated: v0.8
---
**What it does:** short cards have a minimum width (they never squeeze) and, with **Fill the row** (v0.8, on by default), stretch evenly to fill the full width; with it off they keep exactly the width. One of three layouts: **A** tag bars under the Enrich button on the right, **B** the same on the left, **C** on the name line. Each directory can choose its own; the default is in Settings → Display.

## How it works
- `common.card_cfg(s, user, group)`: Display defaults (`card_style`, `card_width`, `card_tint`, `card_fill`, `per_row` = at most N per row) overridden by `groups.card` (`style`, `width`, `tint`, `fill`).
- Grid CSS: exact width `.grid.cards { grid-template-columns: repeat(auto-fill, var(--cardw)) }` (+ `max-width` for N per row); **fill** `.grid.cards.fill { repeat(auto-fill, minmax(var(--cardw), 1fr)) }`; fill + N per row (`.rowcap`, `--perrow`) uses `minmax(max(var(--cardw), (100% - (N-1)·12px) / N), 1fr)`, so the N cards share the width. One column on phones.
- **Short Card Shows…** on the big card (`/records/<id>/cardfields`): up to 3 fields for every card in the directory (sets `fields.card`, needs *Manage directories*) or only for me (`users.prefs.cardfields[<directory id>]`). `common.card_fields()` picks them.

## Files
`app/web/common.py`, `templates/contacts.html`, `dir_edit.html` (Cards section), `display.html`.
