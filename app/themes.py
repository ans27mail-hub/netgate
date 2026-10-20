"""Themes: colours, fonts, corners and spacing. A theme is only settings (no code); the page layout stays the same.
The stylesheet uses CSS variables (`--ink`, `--card`, `--side` …); a theme sets them in a small <style> block.

v0.9 (like BrandPartners' Appearance settings): ready-made colour sets A–D, a heading font and a body font from a
longer list, fonts uploaded as files (served by NetGate, so they work without internet), text size, and each
person's own look (Settings → Display)."""
import re

# The 8 colours a person chooses; every other shade is worked out from these.
COLOURS = [("side", "Menu (left)"), ("side_text", "Menu text"), ("bg", "Page background"), ("card", "Cards"),
           ("line", "Lines"), ("ink", "Text"), ("muted", "Grey text"), ("accent", "Accent (buttons, links)")]
FONTS = {
    "Instrument Sans": "Instrument+Sans:wght@400;500;600;700",
    "Archivo": "Archivo:wght@400;500;600;700",
    "Public Sans": "Public+Sans:wght@400;500;600;700",
    "IBM Plex Sans": "IBM+Plex+Sans:wght@400;500;600;700",
    "Inter": "Inter:wght@400;500;600;700",
    "Poppins": "Poppins:wght@400;500;600;700",
    "Montserrat": "Montserrat:wght@400;500;600;700",
    "Roboto": "Roboto:wght@400;500;700",
    "Lato": "Lato:wght@400;700",
    "Open Sans": "Open+Sans:wght@400;500;600;700",
    "Source Sans 3": "Source+Sans+3:wght@400;500;600;700",
    "Playfair Display": "Playfair+Display:wght@400;600;700",
    "Source Serif 4": "Source+Serif+4:wght@400;600;700",
    "Noto Sans (also Urdu)": "Noto+Sans:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@400;700",
}
FONT_STACK = {"Noto Sans (also Urdu)": "'Noto Sans', 'Noto Nastaliq Urdu'"}
SERIF = {"Playfair Display", "Source Serif 4"}
SIZES = {"small": ("Smaller", -1), "normal": ("Normal", 0), "large": ("Larger", 1), "xlarge": ("Largest", 2)}
CORNERS = {"round": ("Round", 14, 8), "slight": ("Slightly round", 8, 6), "square": ("Square", 3, 3)}
SPACING = {"normal": ("Normal", 15), "compact": ("Compact (more on screen)", 14), "roomy": ("Roomy", 16)}

def _light(side: str, accent: str, bg: str, side_text: str = "#d5dae3") -> dict:
    return {"side": side, "side_text": side_text, "bg": bg, "card": "#ffffff", "line": "#e3e6eb", "ink": "#16181d",
            "muted": "#5b6170", "accent": accent}


BUILTIN = {
    "classic": {"id": "classic", "name": "NetGate Classic", "builtin": True,
                "colors": {"side": "#16181d", "side_text": "#cfd3db", "bg": "#f4f6f9", "card": "#ffffff",
                           "line": "#e3e6eb", "ink": "#16181d", "muted": "#5b6170", "accent": "#2457d6"},
                "font": "Instrument Sans", "heading_font": "", "corners": "round", "spacing": "normal"},
    "dark": {"id": "dark", "name": "Dark", "builtin": True,
             "colors": {"side": "#0d0f12", "side_text": "#c3c8d1", "bg": "#1b1e24", "card": "#23272e",
                        "line": "#363b44", "ink": "#e8eaee", "muted": "#9aa1ad", "accent": "#6e9bff"},
             "font": "Instrument Sans", "heading_font": "", "corners": "round", "spacing": "normal"},
    # v0.9: the colour sets of BrandPartners (Settings → Appearance), with its fonts Archivo + Public Sans
    "bp-a": {"id": "bp-a", "name": "A · Navy and Amber", "builtin": True,
             "colors": _light("#14213d", "#f2a33a", "#f4f5f7"), "font": "Public Sans", "heading_font": "Archivo",
             "corners": "round", "spacing": "normal"},
    "bp-b": {"id": "bp-b", "name": "B · Graphite and Racing Red", "builtin": True,
             "colors": _light("#1a1c20", "#c8232b", "#f4f4f5"), "font": "Public Sans", "heading_font": "Archivo",
             "corners": "round", "spacing": "normal"},
    "bp-c": {"id": "bp-c", "name": "C · Deep Teal and Copper", "builtin": True,
             "colors": _light("#123b3c", "#d9773a", "#f3f5f4"), "font": "Public Sans", "heading_font": "Archivo",
             "corners": "round", "spacing": "normal"},
    "bp-d": {"id": "bp-d", "name": "D · Charcoal and Blue", "builtin": True,
             "colors": _light("#111827", "#2d5be3", "#f4f5f7"), "font": "Public Sans", "heading_font": "Archivo",
             "corners": "round", "spacing": "normal"},
}
# colour sets offered as “start from” buttons when editing a theme (and in Display)
PRESETS = [(k, t["name"], t["colors"]) for k, t in BUILTIN.items()]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------- colour maths ----------

def rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hexc(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def mix(a: str, b: str, t: float) -> str:
    """a mixed with b; t = share of b."""
    ra, rb = rgb(a), rgb(b)
    return hexc([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def lum(h: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def is_dark(t: dict) -> bool:
    return lum(t["colors"]["bg"]) < 0.2


# ---------- themes ----------

def all_themes(saved: list | None, uploaded=()) -> list[dict]:
    return list(BUILTIN.values()) + [clean(t, uploaded) for t in (saved or []) if t.get("id") not in BUILTIN]


def get(saved: list | None, theme_id: str | None, uploaded=()) -> dict:
    for t in all_themes(saved, uploaded):
        if t["id"] == theme_id:
            return t
    return BUILTIN["classic"]


def font_ok(name, uploaded=()) -> bool:
    return bool(name) and (name in FONTS or name in set(uploaded))


def clean(t: dict, uploaded=()) -> dict:
    base = BUILTIN["classic"]
    colors = {k: (v if HEX.match(str(v or "")) else base["colors"][k])
              for k, v in {**base["colors"], **(t.get("colors") or {})}.items() if k in base["colors"]}
    hf = t.get("heading_font") or ""
    return {"id": str(t.get("id") or "custom"), "name": str(t.get("name") or "My theme")[:60], "builtin": False,
            "colors": colors, "font": t.get("font") if font_ok(t.get("font"), uploaded) else "Instrument Sans",
            "heading_font": hf if font_ok(hf, uploaded) else "",
            "corners": t.get("corners") if t.get("corners") in CORNERS else "round",
            "spacing": t.get("spacing") if t.get("spacing") in SPACING else "normal"}


def with_look(t: dict, look: dict | None, uploaded=()) -> dict:
    """A person's own fonts and text size (Settings → Display) on top of a theme."""
    look = look or {}
    out = dict(t)
    if font_ok(look.get("font"), uploaded):
        out["font"] = look["font"]
    if font_ok(look.get("heading_font"), uploaded):
        out["heading_font"] = look["heading_font"]
    if look.get("size") in SIZES:
        out["size"] = look["size"]
    return out


def stack(name: str) -> str:
    fam = FONT_STACK.get(name, f"'{name}'")
    return fam + (", Georgia, serif" if name in SERIF else ", system-ui, sans-serif")


def warnings(t: dict) -> list[str]:
    """Plain-English warnings when text would be hard to read."""
    c, out = t["colors"], []
    if contrast(c["ink"], c["bg"]) < 4.5 or contrast(c["ink"], c["card"]) < 4.5:
        out.append("Text and background are too close in colour — text may be hard to read.")
    if contrast(c["muted"], c["card"]) < 3:
        out.append("Grey text is very light on the cards.")
    if contrast(c["side_text"], c["side"]) < 4.5:
        out.append("Menu text and menu colour are too close.")
    return out


def on_color(bg: str) -> str:
    """White or dark text, whichever reads better on this colour (like BrandPartners' textOn)."""
    return "#ffffff" if contrast("#ffffff", bg) >= contrast("#16181d", bg) else "#16181d"


def variables(t: dict) -> dict[str, str]:
    c = t["colors"]
    dark = is_dark(t)
    radius, radius_sm = CORNERS[t["corners"]][1:]
    return {
        "--ink": c["ink"], "--ink-2": mix(c["ink"], c["bg"], 0.25), "--muted": c["muted"],
        "--muted-2": mix(c["muted"], c["card"], 0.3),
        "--line": c["line"], "--line-2": mix(c["line"], c["card"], 0.45),
        "--line-strong": mix(c["line"], c["ink"], 0.22 if not dark else 0.18),
        "--bg": c["bg"], "--card": c["card"], "--field": c["card"] if not dark else mix(c["card"], c["bg"], 0.5),
        "--accent": c["accent"], "--accent-dark": mix(c["accent"], "#000000", 0.15),
        "--accent-ink": mix(c["accent"], "#000000", 0.2) if not dark else mix(c["accent"], "#ffffff", 0.3),
        "--accent-soft": mix(c["card"], c["accent"], 0.1 if not dark else 0.18),
        "--accent-line": mix(c["card"], c["accent"], 0.3),
        "--side": c["side"], "--side-text": c["side_text"], "--side-muted": mix(c["side_text"], c["side"], 0.4),
        "--side-hi": mix(c["side"], c["side_text"], 0.13), "--side-hover": mix(c["side"], c["side_text"], 0.08),
        "--side-line": mix(c["side"], c["side_text"], 0.16),
        "--radius": f"{radius}px", "--radius-md": f"{max(3, radius - 2)}px", "--radius-sm": f"{radius_sm}px",
        "--font": stack(t["font"]),
        "--display": stack(t.get("heading_font") or t["font"]),
        "--fs": f"{SPACING[t['spacing']][1] + SIZES.get(t.get('size') or 'normal', SIZES['normal'])[1]}px",
        "--accent-fg": on_color(c["accent"]),
        "color-scheme": "dark" if dark else "light",
    }


def css(t: dict, dark_follow: dict | None = None, uploaded: dict | None = None) -> str:
    """The <style> text for a theme (and, optionally, the Dark theme when the computer is in dark mode).
    `uploaded` = {font name: file id} of fonts uploaded in Settings → Themes."""
    body = ";".join(f"{k}:{v}" for k, v in variables(t).items())
    out = ""
    for name, fid in (uploaded or {}).items():
        if name in (t.get("font"), t.get("heading_font")):
            safe = name.replace("'", "").replace("\\", "").replace("<", "")
            out += f"@font-face{{font-family:'{safe}';src:url('/fonts/{fid}');font-display:swap}}"
    out += f":root{{{body}}}"
    if dark_follow:
        dark = ";".join(f"{k}:{v}" for k, v in variables(dark_follow).items())
        out += f"@media (prefers-color-scheme: dark){{:root{{{dark}}}}}"
    return out


def font_url(*themes) -> str:
    fams = sorted({FONTS[f] for t in themes if t for f in (t.get("font"), t.get("heading_font")) if f in FONTS})
    if not fams:
        return ""
    return "https://fonts.googleapis.com/css2?" + "&".join(f"family={f}" for f in fams) + "&display=swap"
