---
title: Card styles and short-card fields
order: 75
updated: v0.7
---
**What it does:** short cards have a fixed width (they never squeeze) and one of three layouts: **A** tag bars under the Enrich button on the right, **B** the same on the left, **C** on the name line. Each directory can choose its own; the default is in Settings → Display.

## How it works
- `common.card_cfg(s, user, group)`: Display defaults (`card_style`, `card_width`, `card_tint`, `per_row` = at most N per row) overridden by `groups.card`.
- Grid CSS: `.grid.cards { grid-template-columns: repeat(auto-fill, var(--cardw)) }`; one column on phones.
- **Short Card Shows…** on the big card (`/records/<id>/cardfields`): up to 3 fields for every card in the directory (sets `fields.card`, needs *Manage directories*) or only for me (`users.prefs.cardfields[<directory id>]`). `common.card_fields()` picks them.

## Files
`app/web/common.py`, `templates/contacts.html`, `dir_edit.html` (Cards section), `display.html`.
