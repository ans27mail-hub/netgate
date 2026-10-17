---
title: Themes
order: 100
updated: v0.7
---
**What it does:** Settings → Themes: a theme for everyone, optional personal themes (Settings → Display), “use Dark when the computer is in dark mode”, and own themes made by copying one and changing 8 colours, font, corners and spacing, with a live preview and readability warnings.

## How it works
- The stylesheet uses CSS variables (`--ink`, `--card`, `--line`, `--accent`, `--side` …, `--radius`, `--font`, `--fs`). `themes.variables()` works out every shade from the 8 chosen colours; `common.theme_for()` picks the person's theme; `base.html` adds a small `<style>:root{…}</style>` and the font link.
- Built-in: NetGate Classic, Dark. Own themes are stored in setting `themes`; the choice for everyone in `theme`; a person's choice in `users.prefs.theme`.
- `themes.warnings()` checks contrast (text 4.5:1, white on accent 3:1).
- Themes are settings only, never code.

## Limits
Some small coloured badges keep light colours in Dark. A completely different layout needs code (GitHub).

## Files
`app/themes.py`, `app/web/look_routes.py`, `templates/themes.html`, `app/static/app.css` (top: variables).
