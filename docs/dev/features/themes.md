---
title: Themes
order: 100
updated: v0.9
---
**What it does:** Settings → Themes: a theme for everyone, optional personal themes (Settings → Display), “use Dark when the computer is in dark mode”, and own themes made by copying one and changing 8 colours, font, corners and spacing, with a live preview and readability warnings.

## How it works
- The stylesheet uses CSS variables (`--ink`, `--card`, `--line`, `--accent`, `--side` …, `--radius`, `--font`, `--fs`). `themes.variables()` works out every shade from the 8 chosen colours; `common.theme_for()` picks the person's theme; `base.html` adds a small `<style>:root{…}</style>` and the font link.
- Built-in: NetGate Classic, Dark. Own themes are stored in setting `themes`; the choice for everyone in `theme`; a person's choice in `users.prefs.theme`.
- `themes.warnings()` checks contrast (text 4.5:1, white on accent 3:1).
- Themes are settings only, never code.

## v0.9 — colour sets, two fonts, uploaded fonts, My Look
- Built-in themes `bp-a` … `bp-d` = BrandPartners' colour presets (Navy and Amber, Graphite and Racing Red, Deep Teal and Copper, Charcoal and Blue) with Archivo + Public Sans; `themes.PRESETS` feeds the “Start from a colour set” buttons.
- A theme has `font` (text) and `heading_font` (`--display`, used by h1–h3 and the brand); `FONTS` has 14 Google fonts; uploaded fonts (`font_files`, Settings → Themes → Fonts, `/fonts/<id>`, max 3 MB) are allowed wherever a font is (`themes.font_ok`) and get an `@font-face` in the theme CSS.
- `--accent-fg` = white or dark text on the accent (`themes.on_color`), used by primary buttons and badges.
- **My Look**: `users.prefs.theme` + `users.prefs.look` (`font`, `heading_font`, `size` small/normal/large/xlarge → `--fs` ±1–2 px); `common.theme_for()` applies it with `themes.with_look()` when personal looks are allowed. Saved by `/settings/display/look`.

## Limits
Some small coloured badges keep light colours in Dark. A completely different layout needs code (GitHub).

## Files
`app/themes.py`, `app/web/look_routes.py`, `templates/themes.html`, `app/static/app.css` (top: variables).
