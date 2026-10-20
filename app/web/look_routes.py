"""Settings → Tags and Settings → Themes."""
import os
import re
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from .. import tags as TG
from .. import themes as TH
from ..auth import can
from ..db import FontFile, RecordTag, SessionLocal, Tag, get_setting, set_setting
from .common import all_groups, current_user, flash, go, render, require, uploaded_fonts

router = APIRouter()
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------- Tags ----------

@router.get("/settings/tags", response_class=HTMLResponse)
def tags_page(request: Request, edit: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_tags")
        tags = TG.all_tags(s)
        counts = dict(s.execute(select(RecordTag.tag_id, func.count(RecordTag.record_id))
                                .group_by(RecordTag.tag_id)).all())
        cur = next((t for t in tags if t.id == edit), None)
        return render(request, s, user, "tags.html", active_nav="tags", help="tags", tags=tags, counts=counts,
                      cur=cur, palette=TG.PALETTE, all=all_groups(s), soft=TG.soft)


def _tag_from_form(form, tag):
    name = str(form.get("name") or "").strip()[:60]
    color = str(form.get("custom") or "").strip() or str(form.get("color") or "")
    tag.name = name or tag.name
    tag.color = color if HEX.match(color) else (tag.color or "#2457d6")
    tag.description = str(form.get("description") or "").strip()[:300]
    tag.color_card = form.get("color_card") == "on"
    tag.all_groups = form.get("where") != "some"
    tag.group_ids = [int(g) for g in form.getlist("groups") if str(g).isdigit()] if not tag.all_groups else []


@router.post("/settings/tags/new")
async def tag_new(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_tags")
        name = str(form.get("name") or "").strip()[:60]
        if not name or s.scalar(select(Tag).where(func.lower(Tag.name) == name.lower())):
            flash(request, "Give the tag a new, unique name.", True)
            return go("/settings/tags")
        pos = (s.scalar(select(func.max(Tag.position))) or 0) + 1
        tag = Tag(name=name, position=pos, color="#2457d6", color_card=True, all_groups=True, group_ids=[])
        _tag_from_form(form, tag)
        s.add(tag)
        s.commit()
        flash(request, f"Tag “{tag.name}” created.")
        return go(f"/settings/tags?edit={tag.id}")


@router.post("/settings/tags/{tid}")
async def tag_save(request: Request, tid: int):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_tags")
        tag = s.get(Tag, tid)
        if not tag:
            return go("/settings/tags")
        action = str(form.get("action") or "save")
        tags = TG.all_tags(s)
        if action in ("up", "down"):
            i = next(i for i, t in enumerate(tags) if t.id == tid)
            j = i - 1 if action == "up" else i + 1
            if 0 <= j < len(tags):
                tags[i], tags[j] = tags[j], tags[i]
            for n, t in enumerate(tags):
                t.position = n
            s.commit()
            return go("/settings/tags")
        if action == "delete":
            n = s.scalar(select(func.count()).select_from(RecordTag).where(RecordTag.tag_id == tid)) or 0
            name = tag.name
            s.delete(tag)
            s.commit()
            flash(request, f"Tag “{name}” deleted. It was taken off {n} contact{'s' if n != 1 else ''}; "
                           "the contacts themselves are kept.")
            return go("/settings/tags")
        if action == "merge":
            into = s.get(Tag, int(form.get("into") or 0))
            if not into or into.id == tid:
                flash(request, "Choose another tag to merge into.", True)
                return go(f"/settings/tags?edit={tid}")
            have = set(s.scalars(select(RecordTag.record_id).where(RecordTag.tag_id == into.id)).all())
            moved = 0
            for rt in s.scalars(select(RecordTag).where(RecordTag.tag_id == tid)).all():
                if rt.record_id not in have:
                    s.add(RecordTag(record_id=rt.record_id, tag_id=into.id, added_by=user.id))
                    moved += 1
                s.delete(rt)
            name = tag.name
            s.flush()
            s.delete(tag)
            s.commit()
            flash(request, f"“{name}” merged into “{into.name}” ({moved} contact{'s' if moved != 1 else ''} moved).")
            return go(f"/settings/tags?edit={into.id}")
        new_name = str(form.get("name") or "").strip()[:60]
        if new_name and s.scalar(select(Tag).where(func.lower(Tag.name) == new_name.lower(), Tag.id != tid)):
            flash(request, "Another tag already has that name.", True)
            return go(f"/settings/tags?edit={tid}")
        _tag_from_form(form, tag)
        s.commit()
        flash(request, f"Tag “{tag.name}” saved.")
        return go(f"/settings/tags?edit={tid}")


# ---------- Themes ----------

FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}
MAX_FONT = 3 * 1024 * 1024


@router.post("/settings/themes/fonts")
async def font_upload(request: Request):
    """Install a font file (v0.9): kept in NetGate's database and served by NetGate, so it works offline."""
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "display_all")
        if form.get("delete"):
            row = s.get(FontFile, int(form.get("delete")) if str(form.get("delete")).isdigit() else 0)
            if row:
                s.delete(row)
                s.commit()
                flash(request, f"Font “{row.name}” removed. Themes that used it fall back to Instrument Sans.")
            return go("/settings/themes#fonts")
        up = form.get("file")
        name = re.sub(r"[^A-Za-z0-9 \-]", "", str(form.get("name") or "")).strip()[:60]
        ext = os.path.splitext(getattr(up, "filename", "") or "")[1].lower()
        if not up or ext not in FONT_TYPES:
            flash(request, "Choose a font file: .woff2, .woff, .ttf or .otf.", True)
            return go("/settings/themes#fonts")
        data = await up.read()
        if not data or len(data) > MAX_FONT:
            flash(request, "That file is empty or bigger than 3 MB.", True)
            return go("/settings/themes#fonts")
        name = name or re.sub(r"[^A-Za-z0-9 \-]", " ", os.path.splitext(up.filename)[0]).strip()[:60] or "My font"
        if name in TH.FONTS or s.scalar(select(FontFile).where(FontFile.name == name)):
            flash(request, f"There is already a font called “{name}”. Give it another name.", True)
            return go("/settings/themes#fonts")
        s.add(FontFile(name=name, mime=FONT_TYPES[ext], data=data))
        s.commit()
        flash(request, f"Font “{name}” installed. Choose it as a theme's text or heading font.")
    return go("/settings/themes#fonts")


@router.get("/fonts/{fid}")
def font_file(fid: int):
    with SessionLocal() as s:
        row = s.get(FontFile, fid)
        if not row:
            return Response(status_code=404)
        return Response(row.data, media_type=row.mime, headers={"Cache-Control": "public, max-age=604800"})


def theme_settings(s) -> dict:
    return {"default": "classic", "allow_personal": True, "follow_dark": False, **(get_setting(s, "theme", {}) or {})}


@router.get("/settings/themes", response_class=HTMLResponse)
def themes_page(request: Request, edit: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "display_all")
        saved = get_setting(s, "themes", []) or []
        fonts = uploaded_fonts(s)
        themes = TH.all_themes(saved, fonts)
        cur = TH.get(saved, edit, fonts) if edit else None
        if cur and cur["id"] != edit:
            cur = None
        return render(request, s, user, "themes.html", active_nav="themes", help="themes", themes=themes,
                      cfg=theme_settings(s), cur=cur, COLOURS=TH.COLOURS, FONTS=TH.FONTS, CORNERS=TH.CORNERS,
                      font_names=list(TH.FONTS) + [f for f in fonts if f not in TH.FONTS], uploaded=fonts,
                      PRESETS=TH.PRESETS,
                      SPACING=TH.SPACING, warnings=TH.warnings(cur) if cur else [], all=all_groups(s))


@router.post("/settings/themes")
async def themes_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        action = str(form.get("action") or "")
        fonts = uploaded_fonts(s)
        saved = [TH.clean(t, fonts) for t in (get_setting(s, "themes", []) or [])]
        ids = {t["id"] for t in TH.all_themes(saved, fonts)}
        if action == "mine":   # anyone allowed: try a theme for themselves
            cfg = theme_settings(s)
            tid = str(form.get("id") or "")
            if (cfg["allow_personal"] or can(user, "display_all")) and (tid in ids or tid == ""):
                user.prefs = {**(user.prefs or {}), "theme": tid}
                s.commit()
                flash(request, "Theme changed for you." if tid else "You now use the theme for everyone.")
            return go(request.headers.get("referer") or "/settings/display")
        require(user, "display_all")
        if action == "settings":
            tid = str(form.get("default") or "classic")
            set_setting(s, "theme", {"default": tid if tid in ids else "classic",
                                     "allow_personal": form.get("allow_personal") == "on",
                                     "follow_dark": form.get("follow_dark") == "on"})
            s.commit()
            flash(request, "Theme settings saved.")
            return go("/settings/themes")
        if action == "use":
            cfg = theme_settings(s)
            tid = str(form.get("id") or "")
            cfg["default"] = tid if tid in ids else "classic"
            set_setting(s, "theme", cfg)
            s.commit()
            flash(request, "This theme is now used by everyone (people who chose their own keep theirs).")
            return go("/settings/themes")
        if action == "copy":
            src = TH.get(saved, str(form.get("id") or ""), fonts)
            new = TH.clean({**src, "id": "t" + uuid.uuid4().hex[:8], "name": f"{src['name']} (copy)"}, fonts)
            saved.append(new)
            set_setting(s, "themes", saved)
            s.commit()
            flash(request, f"“{new['name']}” created. Change its colours below.")
            return go(f"/settings/themes?edit={new['id']}")
        tid = str(form.get("id") or "")
        idx = next((i for i, t in enumerate(saved) if t["id"] == tid), None)
        if idx is None:
            flash(request, "Built-in themes can't be changed; copy one first.", True)
            return go("/settings/themes")
        if action == "delete":
            name = saved[idx]["name"]
            saved.pop(idx)
            set_setting(s, "themes", saved)
            cfg = theme_settings(s)
            if cfg["default"] == tid:
                cfg["default"] = "classic"
                set_setting(s, "theme", cfg)
            s.commit()
            flash(request, f"Theme “{name}” deleted. Anyone using it is back on the theme for everyone.")
            return go("/settings/themes")
        t = saved[idx]
        t["name"] = str(form.get("name") or t["name"]).strip()[:60] or t["name"]
        for key, _ in TH.COLOURS:
            v = str(form.get(f"c_{key}") or "").strip()
            if HEX.match(v):
                t["colors"][key] = v.lower()
        for key, opts in (("corners", TH.CORNERS), ("spacing", TH.SPACING)):
            if form.get(key) in opts:
                t[key] = form.get(key)
        if TH.font_ok(form.get("font"), fonts):
            t["font"] = form.get("font")
        if form.get("heading_font") is not None:
            hf = str(form.get("heading_font") or "")
            t["heading_font"] = hf if TH.font_ok(hf, fonts) else ""
        saved[idx] = TH.clean(t, fonts)
        set_setting(s, "themes", saved)
        if action == "try":
            user.prefs = {**(user.prefs or {}), "theme": tid}
        s.commit()
        warn = TH.warnings(saved[idx])
        flash(request, ("Saved, and you now see it." if action == "try" else "Theme saved.")
              + (" Careful: " + " ".join(warn) if warn else ""), bool(warn))
        return go(f"/settings/themes?edit={tid}")
