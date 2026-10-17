"""Settings: directories (methods, fields, instructions, keywords), AI, night jobs, display, crawler,
connections and the reject list."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from .. import ai, control, crawl, ebay, methods
from .. import themes as TH
from ..auth import can, can_any
from ..db import (EMPLOYEE_RANGES, FIELD_TYPES, AIServer, Field, Group, Keyword, Membership, NightRun, PageCache,
                  RejectedKeyword, SessionLocal, User, get_setting, set_setting, slugify)
from ..jobs import NIGHT_DEFAULTS, Ctx, _ask_entries, _enhance_entries, night_settings
from .common import (CARD_STYLES, DISPLAY_DEFAULTS, Forbidden, all_groups, back, current_user, flash, go, render, require)

router = APIRouter()

SETTINGS_PAGES = [("manage_dirs", "/settings/directories"), ("ai", "/settings/ai"), ("night", "/settings/night"),
                  ("crawler", "/settings/crawler"), ("connections", "/settings/connections"),
                  ("manage_users", "/settings/users"), ("manage_roles", "/settings/roles"),
                  ("reject_list", "/settings/reject-list"), ("manage_tags", "/settings/tags"),
                  ("display_all", "/settings/themes"), ("backups", "/settings/backups")]

# (key, name, type, stage, filter, card, list, source, choices, words)
PRESET_FIELDS = [
    ("city", "City", "text", "discover", True, True, True, "", "", "address, located in"),
    ("country", "Country", "text", "discover", True, True, True, "", "", "address"),
    ("website", "Website", "url", "discover", False, False, True, "", "", "official website"),
    ("contact_email", "Email", "email", "enrich", True, False, True, "", "", "contact, email, enquiry"),
    ("phone", "Phone", "phone", "enrich", False, False, True, "", "", "phone, contact, call"),
    ("whatsapp", "WhatsApp", "text", "enrich", False, False, False, "", "", "whatsapp"),
    ("address", "Address", "text", "enrich", False, False, False, "", "", "address"),
    ("products", "Products", "list", "enrich", True, True, True, "", "", "products, we manufacture, product range"),
    ("employees", "Employees", "choice", "enrich", True, True, True, "", EMPLOYEE_RANGES,
     "employees, staff, workers, workforce"),
    ("sells_on", "Sells on", "list", "discover", True, True, True, "method:marketplace", "", ""),
    ("seller_rating", "Seller rating", "text", "discover", True, True, True, "ebay:feedback_pct", "", ""),
    ("feedback_count", "Feedback count", "number", "discover", True, False, True, "ebay:feedback_score", "", ""),
    ("business_name", "Business name", "text", "enrich", False, False, False, "ebay:business_name", "", ""),
    ("certifications", "Certifications", "list", "enrich", True, False, False, "", "", "ISO, CE, certified"),
]
DEFAULT_PRESETS = ["city", "country", "website", "contact_email", "phone"]
EBAY_PRESETS = ["sells_on", "seller_rating", "feedback_count", "business_name"]


@router.get("/settings")
def settings_home(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        for perm, url in SETTINGS_PAGES:
            if can(user, perm):
                return go(url)
    return go("/settings/display")


def _int(v, default, lo, hi, cast=int):
    try:
        return min(hi, max(lo, cast(float(v))))
    except (TypeError, ValueError):
        return default


def _methods_from_form(form, old: dict | None = None) -> dict:
    old = old or {}
    out = {}
    for key in methods.METHODS:
        if form.get(f"m_{key}") == "on" and methods.METHODS[key]["ready"]:
            out[key] = dict(old.get(key) or {})
    if "ebay" in out:
        out["ebay"].update({
            "sites": [x for x in form.getlist("ebay_sites") if x in ebay.SITE_HOST],
            "category_id": str(form.get("ebay_category_id") or "").strip()[:20],
            "per_keyword": _int(form.get("ebay_per_keyword"), 200, 10, 2000),
            "min_feedback": _int(form.get("ebay_min_feedback"), 0, 0, 1_000_000),
            "max_sellers": _int(form.get("ebay_max_sellers"), 60, 1, 500),
            "business_only": form.get("ebay_business_only") == "on",
        })
    if "directory" in out:
        out["directory"].update({"start_urls": str(form.get("dir_start_urls") or "").strip(),
                                 "sites": str(form.get("dir_sites") or "").strip()})
    if not [k for k in out if methods.METHODS[k]["step"] == "find"]:
        out["web"] = {}
    return out


def _settings_ctx(s):
    return {"all": all_groups(s), "counts": dict(s.execute(select(Membership.group_id, func.count(Membership.record_id))
                                                           .group_by(Membership.group_id)).all())}


# ---------- directories ----------

@router.get("/settings/directories", response_class=HTMLResponse)
def directories_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        groups = all_groups(s)
        if groups:
            return go(f"/settings/directories/{groups[0].id}")
        return go("/settings/directories/new")


@router.get("/settings/groups/{gid}")
def old_group_url(gid: int):
    return go(f"/settings/directories/{gid}")


@router.get("/settings/directories/new", response_class=HTMLResponse)
def new_directory_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        conn = methods.connections(s)
        return render(request, s, user, "dir_new.html", active_nav="dirs", help="new-directory", group=None,
                      presets=PRESET_FIELDS, default_presets=DEFAULT_PRESETS, ebay_presets=EBAY_PRESETS,
                      ebay_sites=ebay.EBAY_SITES, conn=conn, **_settings_ctx(s))


@router.post("/settings/directories")
async def create_directory(request: Request):
    form = await request.form()
    name = str(form.get("name") or "").strip()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        if not name or s.scalar(select(Group).where(Group.name == name)):
            flash(request, "Give the directory a new, unique name.", True)
            return go("/settings/directories/new")
        position = (s.scalar(select(func.max(Group.position))) or 0) + 1
        g = Group(name=name[:120], description=str(form.get("description") or "").strip()[:500], position=position,
                  instructions=str(form.get("instructions") or "").strip(),
                  enrich_instructions=str(form.get("enrich_instructions") or "").strip(),
                  ignore_instructions=str(form.get("ignore_instructions") or "").strip(),
                  search_terms=str(form.get("search_terms") or "").strip(), methods=_methods_from_form(form),
                  owner_id=user.id, card={})
        picked = set(form.getlist("presets")) or set(DEFAULT_PRESETS)
        g.fields = []
        pos = 0
        for key, fname, ftype, stage, flt, card, lst, source, choices, words in PRESET_FIELDS:
            if key in picked:
                pos += 1
                g.fields.append(Field(name=fname, key=key, type=ftype, stage=stage, filter=flt, card=card, list=lst,
                                      source=source if (not source.startswith("ebay") or "ebay" in g.methods)
                                      and (source != "method:marketplace" or "ebay" in g.methods) else "",
                                      choices=choices, words=words, position=pos))
        night = form.get("night") == "on"
        seen = set()
        for part in str(form.get("keywords") or "").replace("\n", ",").split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                g.keywords.append(Keyword(text=part[:300], night=night, method="all", found_count=0))
        s.add(g)
        s.commit()
        flash(request, f"Directory “{name}” created. Fine-tune fields, methods and keywords below, "
                       "or start searching from the Inbox.")
        return go(f"/settings/directories/{g.id}")


def _dir_page(request, s, user, group, **extra):
    conn = methods.connections(s)
    owners = s.scalars(select(User).where(User.active).order_by(User.username)).all()
    return render(request, s, user, "dir_edit.html", active_nav="dirs", help="directory-settings", group=group,
                  owners=owners,
                  count=_settings_ctx(s)["counts"].get(group.id, 0), ebay_sites=ebay.EBAY_SITES, conn=conn,
                  opts={k: methods.options(group, k) for k in ("ebay", "directory")}, **_settings_ctx(s), **extra)


@router.get("/settings/directories/{gid}", response_class=HTMLResponse)
def directory_edit(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        group = s.get(Group, gid)
        if not group:
            return go("/settings/directories")
        return _dir_page(request, s, user, group)


@router.post("/settings/directories/{gid}")
async def directory_save(request: Request, gid: int):
    form = await request.form()
    section = str(form.get("section") or "basics")
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        group = s.get(Group, gid)
        if not group:
            return go("/settings/directories")
        if section == "basics":
            name = str(form.get("name", "")).strip()
            clash = s.scalar(select(Group).where(Group.name == name, Group.id != gid))
            if not name or clash:
                flash(request, "That name is empty or already used.", True)
                return go(f"/settings/directories/{gid}")
            group.name, group.description = name, str(form.get("description") or "").strip()[:500]
            group.position = _int(form.get("position"), 0, -1000, 1000)
            group.search_terms = str(form.get("search_terms", "")).strip()
            group.methods = _methods_from_form(form, group.methods)
            oid = str(form.get("owner_id") or "")
            group.owner_id = int(oid) if oid.isdigit() and s.get(User, int(oid)) else None
            flash(request, "Basics and search methods saved.")
        elif section == "cards":
            style = str(form.get("card_style") or "")
            tint = str(form.get("card_tint") or "")
            width = str(form.get("card_width") or "").strip()
            card = {}
            if style in CARD_STYLES:
                card["style"] = style
            if width.isdigit():
                card["width"] = _int(width, 260, 180, 520)
            if tint in ("on", "off"):
                card["tint"] = tint == "on"
            group.card = card
            flash(request, "Card look saved for this directory.")
        else:
            group.instructions = str(form.get("instructions", "")).strip()
            group.enrich_instructions = str(form.get("enrich_instructions", "")).strip()
            group.ignore_instructions = str(form.get("ignore_instructions", "")).strip()
            flash(request, "Instructions saved.")
        s.commit()
    return go(f"/settings/directories/{gid}#{section}")


@router.post("/settings/directories/{gid}/delete")
def directory_delete(request: Request, gid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        group = s.get(Group, gid)
        if group:
            s.delete(group)
            s.commit()
            flash(request, f"Directory “{group.name}” deleted. Its contacts are kept in All contacts.")
    return go("/settings/directories")


@router.post("/settings/directories/{gid}/keywords")
def keyword_add(request: Request, gid: int, text: str = Form(...), method: str = Form("all")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        group = s.get(Group, gid)
        existing = {k.text.lower() for k in group.keywords}
        method = method if method == "all" or method in methods.FIND_METHODS else "all"
        added, blocked = 0, []
        for part in text.replace("\n", ",").split(","):
            part = part.strip()
            if not part or part.lower() in existing:
                continue
            if control.rejected_entry(s, part, gid):
                blocked.append(part)
                continue
            group.keywords.append(Keyword(text=part[:300], night=True, method=method, found_count=0))
            existing.add(part.lower())
            added += 1
        s.commit()
        if blocked:
            flash(request, f"Not added (on the reject list): {', '.join(blocked)}.", True)
    return go(f"/settings/directories/{gid}#keywords")


@router.post("/settings/directories/{gid}/keywords/{kid}")
def keyword_save(request: Request, gid: int, kid: int, method: str = Form(""), night: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            if method:
                kw.method = method if method == "all" or method in methods.FIND_METHODS else "all"
            if night:
                kw.night = night == "on"
            s.commit()
    return go(f"/settings/directories/{gid}#keywords")


@router.post("/settings/directories/{gid}/keywords/{kid}/delete")
def keyword_delete(request: Request, gid: int, kid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        kw = s.get(Keyword, kid)
        if kw and kw.group_id == gid:
            s.delete(kw)
            s.commit()
    return go(f"/settings/directories/{gid}#keywords")


@router.post("/settings/directories/{gid}/fields")
def field_add(request: Request, gid: int, name: str = Form(...), type: str = Form("text"),
              choices: str = Form(""), words: str = Form(""), stage: str = Form("enrich"), source: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        group = s.get(Group, gid)
        name = name.strip()
        if not name:
            return go(f"/settings/directories/{gid}#fields")
        key, taken, n = slugify(name), {f.key for f in group.fields}, 2
        base = key
        while key in taken:
            key, n = f"{base}_{n}", n + 1
        position = max([f.position for f in group.fields] or [0]) + 1
        group.fields.append(Field(name=name, key=key, type=type if type in FIELD_TYPES else "text",
                                  choices=choices.strip(), words=words.strip(),
                                  stage="discover" if stage == "discover" else "enrich",
                                  source=source if source in methods.SOURCE_LABELS else "",
                                  position=position, card=False, list=True))
        s.commit()
        flash(request, f"Field “{name}” added. Enrich will look for it next time.")
    return go(f"/settings/directories/{gid}#fields")


@router.post("/settings/directories/{gid}/fields/{fid}")
def field_save(request: Request, gid: int, fid: int, name: str = Form(...), type: str = Form("text"),
               choices: str = Form(""), words: str = Form(""), stage: str = Form("enrich"), source: str = Form(""),
               filter: str = Form(""), sort: str = Form(""), card: str = Form(""), list: str = Form(""),
               position: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        f = s.get(Field, fid)
        if f and f.group_id == gid and name.strip():
            f.name, f.type, f.choices = name.strip(), type if type in FIELD_TYPES else "text", choices.strip()
            f.words, f.stage = words.strip(), "discover" if stage == "discover" else "enrich"
            f.source = source if source in methods.SOURCE_LABELS else ""
            f.filter, f.sort, f.card, f.list = bool(filter), bool(sort), bool(card), bool(list)
            if position.lstrip("-").isdigit():
                f.position = int(position)
            s.commit()
            flash(request, f"Field “{f.name}” saved.")
    return go(f"/settings/directories/{gid}#fields")


@router.post("/settings/directories/{gid}/fields/{fid}/delete")
def field_delete(request: Request, gid: int, fid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "manage_dirs")
        f = s.get(Field, fid)
        if f and f.group_id == gid:
            s.delete(f)
            s.commit()
    return go(f"/settings/directories/{gid}#fields")


def page_test(group, url: str, query: str):
    """What Discover would find on one page with the current instructions. Saves nothing."""
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    page = crawl.get_page(url, use_cache=False)
    result, error, info = None, None, ""
    if not page.ok:
        error = f"Could not read that page ({page.note or 'blocked, empty or not HTML'})."
    else:
        ctx = Ctx(None, "discover")
        try:
            result = _ask_entries(ctx, group, query or group.name, page)
            if result:
                _enhance_entries(ctx, page, result)
            nxt = crawl.next_page_url(page.html, page.final_url or url) if result and len(result) >= 3 else None
            info = ("Read with the browser. " if page.rendered else "") \
                + (f"{ctx.stats['profiles']} profile pages opened. " if ctx.stats["profiles"] else "") \
                + (f"Next page found: {nxt}" if nxt else "")
            for e in result:
                found = e.pop("_found", None) or {}
                e.pop("_found_url", None)
                e.pop("_own_site", None)
                e["code"] = ", ".join(x for x in [
                    (found.get("emails") or [None])[0], (found.get("phones") or [None])[0],
                    ", ".join(sorted((found.get("social") or {}).keys())) or None] if x)
        except Exception as e:
            error = f"AI error: {type(e).__name__}: {e}"
    return {"url": url, "entries": result, "error": error, "info": info, "text": (page.text or "")[:3000]}


@router.post("/settings/directories/{gid}/test", response_class=HTMLResponse)
def directory_test(request: Request, gid: int, url: str = Form(...), query: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        if not can_any(user, ["manage_dirs", "tester"]):
            raise Forbidden
        group = s.get(Group, gid)
        _ = group.fields
    test = page_test(group, url, query)
    with SessionLocal() as s:
        user = current_user(s, request)
        group = s.get(Group, gid)
        if not can(user, "manage_dirs"):
            return render(request, s, user, "dev_tester.html", active_nav="dev", help="developer", test=test,
                          groups=all_groups(s), sel_id=gid)
        return _dir_page(request, s, user, group, test=test)


# ---------- AI servers ----------

@router.get("/settings/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        servers = s.scalars(select(AIServer).order_by(AIServer.id)).all()
        models = {sv.id: ai.list_models(sv) for sv in servers if sv.enabled}
        jobs = {j: get_setting(s, f"ai.{j}", {}) or {} for j in list(ai.JOB_TYPES) + ["fallback"]}
        now = datetime.utcnow()
        spend = {"day": ai.spent(s, now - timedelta(hours=24)),
                 "month": ai.spent(s, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))}
        return render(request, s, user, "ai.html", active_nav="ai", help="settings", servers=servers,
                      models=models, jobs=jobs, limits=get_setting(s, "ai.limits", {}) or {}, spend=spend,
                      learn=get_setting(s, "learn", {}) or {}, **_settings_ctx(s))


@router.post("/settings/ai/servers")
def ai_server_add(request: Request, name: str = Form(...), kind: str = Form("ollama"), url: str = Form(""),
                  api_key: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        kind = "openrouter" if kind == "openrouter" else "ollama"
        if kind == "ollama" and not url.strip():
            flash(request, "Enter the server address, e.g. http://192.168.1.60:11434", True)
            return go("/settings/ai")
        s.add(AIServer(name=name.strip() or ("OpenRouter" if kind == "openrouter" else "Ollama"), kind=kind,
                       url=url.strip() if kind == "ollama" else "", api_key=api_key.strip(), enabled=True))
        s.commit()
        flash(request, "Server added. Choose it for a job below, then press Test.")
    return go("/settings/ai")


@router.post("/settings/ai/servers/{sid}")
def ai_server_save(request: Request, sid: int, name: str = Form(...), url: str = Form(""), api_key: str = Form(""),
                   enabled: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        sv = s.get(AIServer, sid)
        if sv:
            sv.name, sv.enabled = name.strip() or sv.name, bool(enabled)
            if sv.kind == "ollama":
                sv.url = url.strip() or sv.url
            if api_key.strip():
                sv.api_key = api_key.strip()
            s.commit()
            flash(request, f"{sv.name} saved.")
    return go("/settings/ai")


@router.post("/settings/ai/servers/{sid}/delete")
def ai_server_delete(request: Request, sid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        sv = s.get(AIServer, sid)
        in_use = [j for j in list(ai.JOB_TYPES) + ["fallback"]
                  if (get_setting(s, f"ai.{j}", {}) or {}).get("server") == sid]
        if sv and in_use:
            flash(request, f"{sv.name} is still used for: {', '.join(in_use)}. Choose another server first.", True)
        elif sv:
            s.delete(sv)
            s.commit()
            flash(request, "Server removed.")
    return go("/settings/ai")


@router.post("/settings/ai/servers/{sid}/test")
def ai_server_test(request: Request, sid: int, model: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        sv = s.get(AIServer, sid)
        if not sv:
            return go("/settings/ai")
        model = model.strip()
        if not model:
            for j in ai.JOB_TYPES:
                conf = get_setting(s, f"ai.{j}", {}) or {}
                if conf.get("server") == sid:
                    model = conf.get("model", "")
                    break
        if not model:
            ms = ai.list_models(sv)
            model = ms[0]["id"] if ms else ""
        if not model:
            flash(request, f"{sv.name}: no models found — is the address right and the server running?", True)
            return go("/settings/ai")
    ok, msg = ai.test_server(sv, model)
    flash(request, f"{sv.name}: {msg}", not ok)
    return go("/settings/ai")


@router.post("/settings/ai/jobs")
async def ai_jobs_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "ai")
        for j in list(ai.JOB_TYPES) + ["fallback"]:
            sid, model = str(form.get(f"{j}_server", "")), str(form.get(f"{j}_model", "")).strip()
            if sid.isdigit() and model:
                set_setting(s, f"ai.{j}", {"server": int(sid), "model": model})

        def num(key):
            try:
                return max(0.0, float(form.get(key) or 0))
            except ValueError:
                return 0.0
        set_setting(s, "ai.limits", {"night": num("limit_night"), "month": num("limit_month")})
        set_setting(s, "learn", {"embed_model": str(form.get("embed_model") or "").strip()[:100]})
        s.commit()
        flash(request, "AI settings saved.")
    return go("/settings/ai")


# ---------- night jobs ----------

@router.get("/settings/night", response_class=HTMLResponse)
def night_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "night")
        runs = s.scalars(select(NightRun).order_by(NightRun.id.desc()).limit(10)).all()
        return render(request, s, user, "night.html", active_nav="night", help="night-jobs",
                      cfg=night_settings(s), runs=runs, **_settings_ctx(s))


@router.post("/settings/night")
async def night_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "night")

        def hhmm(v, default):
            v = str(v or "").strip()
            try:
                h, m = v.split(":")
                return f"{int(h) % 24:02d}:{int(m) % 60:02d}"
            except ValueError:
                return default
        cfg = {
            "enabled": form.get("enabled") == "on",
            "start": hhmm(form.get("start"), NIGHT_DEFAULTS["start"]),
            "stop": hhmm(form.get("stop"), NIGHT_DEFAULTS["stop"]),
            "days": [int(d) for d in form.getlist("days") if str(d).isdigit()],
            "max_companies": _int(form.get("max_companies"), 150, 0, 5000),
            "pause": _int(form.get("pause"), 3, 0, 120),
            "timezone": str(form.get("timezone") or "Asia/Karachi").strip(),
            "enrich_inbox": form.get("enrich_inbox") == "on",
        }
        set_setting(s, "night", cfg)
        for g in all_groups(s):
            g.night_discover = form.get(f"d_{g.id}") == "on"
            g.night_enrich = form.get(f"e_{g.id}") == "on"
            g.refresh_days = _int(form.get(f"r_{g.id}"), 0, 0, 3650)
        s.commit()
        flash(request, "Night jobs saved." + ("" if cfg["enabled"] else " (Night jobs are switched off.)"))
    return go("/settings/night")


# ---------- display ----------

@router.get("/settings/display", response_class=HTMLResponse)
def display_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        everyone = {**DISPLAY_DEFAULTS, **(get_setting(s, "display", {}) or {})}
        mine = (user.prefs or {}).get("display") or {}
        th = get_setting(s, "theme", {}) or {}
        return render(request, s, user, "display.html", active_nav="display", help="settings",
                      everyone=everyone, mine=mine, current={**everyone, **mine}, **_settings_ctx(s),
                      themes=TH.all_themes(get_setting(s, "themes", [])), my_theme=(user.prefs or {}).get("theme") or "",
                      allow_personal=th.get("allow_personal", True), default_theme=th.get("default") or "classic")


@router.post("/settings/display")
async def display_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        d = {"mode": form.get("mode") if form.get("mode") in ("fixed", "pct", "full") else "fixed",
             "px": _int(form.get("px"), 1280, 800, 3000), "pct": _int(form.get("pct"), 90, 50, 100),
             "view": "list" if form.get("view") == "list" else "grid",
             "per_row": _int(form.get("per_row"), 0, 0, 8),
             "card_style": form.get("card_style") if form.get("card_style") in CARD_STYLES else "A",
             "card_width": _int(form.get("card_width"), 260, 180, 520),
             "card_tint": form.get("card_tint") == "on"}
        if form.get("theme") is not None:
            th = get_setting(s, "theme", {}) or {}
            if th.get("allow_personal", True) or can(user, "display_all"):
                user.prefs = {**(user.prefs or {}), "theme": str(form.get("theme") or "")}
        if form.get("scope") == "everyone" and can(user, "display_all"):
            set_setting(s, "display", d)
            prefs = dict(user.prefs or {})
            prefs.pop("display", None)
            user.prefs = prefs
            msg = "Display saved for everyone."
        else:
            user.prefs = {**(user.prefs or {}), "display": d}
            msg = "Display saved for you."
        s.commit()
        flash(request, msg)
    return go("/settings/display")


# ---------- crawler ----------

@router.get("/settings/crawler", response_class=HTMLResponse)
def crawler_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        cfg = {**crawl.CRAWLER_DEFAULTS, **(get_setting(s, "crawler", {}) or {})}
        cache_rows = s.scalar(select(func.count(PageCache.url)))
        renderer_ok = crawl.renderer_status()
        return render(request, s, user, "crawler.html", active_nav="crawler", help="settings", cfg=cfg,
                      cache_rows=cache_rows, renderer_ok=renderer_ok, **_settings_ctx(s))


@router.post("/settings/crawler")
async def crawler_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "crawler")
        d = crawl.CRAWLER_DEFAULTS
        num = lambda key, default, lo, hi, cast=int: _int(form.get(key), default, lo, hi, cast)  # noqa: E731
        cfg = {
            "render": form.get("render") if form.get("render") in ("auto", "never", "always") else "auto",
            "render_domains": str(form.get("render_domains") or "").strip(),
            "skip_domains": str(form.get("skip_domains") or "").strip(),
            "next_pages": num("next_pages", d["next_pages"], 0, 20),
            "directory_mode": form.get("directory_mode") == "on",
            "profiles_per_page": num("profiles_per_page", d["profiles_per_page"], 0, 60),
            "site_pages": num("site_pages", d["site_pages"], 0, 30),
            "cache_days": num("cache_days", d["cache_days"], 0, 30),
            "delay": num("delay", d["delay"], 0, 30, float),
            "robots": form.get("robots") == "on",
            "max_chunks": num("max_chunks", d["max_chunks"], 1, 8),
        }
        set_setting(s, "crawler", cfg)
        s.commit()
        if form.get("clear_cache"):
            n = crawl.purge_cache(0)
            flash(request, f"Crawler settings saved. {n} cached pages cleared.")
        else:
            flash(request, "Crawler settings saved.")
    return go("/settings/crawler")


# ---------- connections ----------

@router.get("/settings/connections", response_class=HTMLResponse)
def connections_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "connections")
        return render(request, s, user, "connections.html", active_nav="connections", help="connections",
                      conn=methods.connections(s), ebay_sites=ebay.EBAY_SITES, **_settings_ctx(s))


@router.post("/settings/connections")
async def connections_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "connections")
        conn = methods.connections(s)

        def keep(new: str, old: str) -> str:   # empty password box = keep the saved value
            new = str(new or "").strip()
            return old if not new else ("" if new == "-" else new)
        conn["ebay"].update({
            "client_id": keep(form.get("ebay_client_id"), conn["ebay"]["client_id"]),
            "client_secret": keep(form.get("ebay_client_secret"), conn["ebay"]["client_secret"]),
            "sites": [x for x in form.getlist("ebay_sites") if x in ebay.SITE_HOST],
            "business_only": form.get("ebay_business_only") == "on",
        })
        conn["etsy"].update({
            "api_key": keep(form.get("etsy_api_key"), conn["etsy"]["api_key"]),
            "shared_secret": keep(form.get("etsy_shared_secret"), conn["etsy"]["shared_secret"]),
        })
        set_setting(s, "connections", conn)
        s.commit()
        msg = "Connections saved."
        if form.get("test") == "ebay":
            try:
                ebay._tokens.clear()
                ebay._token(conn)
                msg = "Connections saved. eBay accepted the keys."
            except Exception as e:
                flash(request, f"Saved, but the eBay test failed: {e}", True)
                return go("/settings/connections")
        flash(request, msg)
    return go("/settings/connections")


# ---------- reject list ----------

@router.get("/settings/reject-list", response_class=HTMLResponse)
def reject_list(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "reject_list")
        rows = s.scalars(select(RejectedKeyword).order_by(RejectedKeyword.at.desc())).all()
        users = {u.id: u.username for u in s.scalars(select(User)).all()}
        return render(request, s, user, "reject_list.html", active_nav="reject", help="requests", rows=rows,
                      users=users, group_names={g.id: g.name for g in all_groups(s)}, **_settings_ctx(s))


@router.post("/settings/reject-list")
def reject_add(request: Request, text: str = Form(...), group_id: str = Form(""), reason: str = Form("")):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "reject_list")
        gid = int(group_id) if group_id.isdigit() else None
        for part in text.replace("\n", ",").split(","):
            if part.strip():
                control.reject_keyword(s, part.strip(), gid, reason, user)
        s.commit()
        flash(request, "Added to the reject list.")
    return go("/settings/reject-list")


@router.post("/settings/reject-list/{rid}/delete")
def reject_remove(request: Request, rid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "reject_list")
        row = s.get(RejectedKeyword, rid)
        if row:
            s.delete(row)
            s.commit()
            flash(request, f"“{row.text}” can be searched again.")
    return back(request, "/settings/reject-list")
