"""Shared helpers for the web pages: templates, login, permissions, the sidebar."""
import hashlib
import os
from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select, true

from .. import ai, control
from .. import themes as TH
from ..auth import (DIR_PERMS, PERM_GROUPS, PERM_KEYS, PERMS, can, can_any, own_contacts_only, sees_all_groups,
                    sees_methods)
from ..contacts import METHOD_LABELS, REJECT_REASONS, completeness_of, empty
from ..db import FIELD_TYPES, Group, InboxItem, Job, Membership, NightRun, Record, User, get_setting
from ..methods import ENRICH_STEPS, FIELD_SOURCES, METHODS, SOURCE_LABELS

VERSION = "v0.8"
BASE = os.path.dirname(os.path.dirname(__file__))
SECRET = os.environ.get("APP_SECRET_KEY") or hashlib.sha256(os.environ["DATABASE_URL"].encode()).hexdigest()
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

DISPLAY_DEFAULTS = {"mode": "fixed", "px": 1280, "pct": 90, "view": "grid", "per_row": 0,
                    "card_style": "A", "card_width": 260, "card_tint": True, "card_fill": True}
CARD_STYLES = {"A": "Right side, under the Enrich button", "B": "Left side, under the Enrich button",
               "C": "In one line with the name"}
CARD_WIDTHS = {"220": "Small (220 px)", "260": "Medium (260 px)", "320": "Large (320 px)"}
SPECIAL_COLS = {"_tags": "Tags", "_dirs": "Directories", "_complete": "Complete", "_updated": "Updated"}


class LoginRequired(Exception):
    pass


class Forbidden(Exception):
    pass


class MustChangePassword(Exception):
    pass


# ---------- formatting ----------

def fmt_value(record, field) -> str:
    v = (record.data or {}).get(field.key)
    if isinstance(v, list):
        return ", ".join(map(str, v)) or "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "—" if v in (None, "") else str(v)


def is_fresh(record) -> bool:
    """Updated (not just added) in the last 7 days."""
    if not record.updated_at or not record.created_at:
        return False
    return (record.updated_at - record.created_at > timedelta(minutes=1)
            and datetime.utcnow() - record.updated_at < timedelta(days=7))


def domain(url: str) -> str:
    return (url or "").split("//")[-1].split("/")[0].removeprefix("www.")


def ago(dt) -> str:
    if not dt:
        return "never"
    secs = (datetime.utcnow() - dt).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    days = int(secs // 86400)
    return "yesterday" if days == 1 else f"{days} days ago"


def pct_class(filled, total) -> str:
    if not total:
        return "good"
    p = filled * 100 / total
    return "good" if p >= 80 else ("low" if p < 50 else "")


def _engine_label(name) -> str:
    from ..engines import label
    return label(str(name))


templates.env.filters["engine_label"] = _engine_label
templates.env.globals.update(
    can=can, can_any=can_any, fmt=fmt_value, fresh=is_fresh, domain=domain, ago=ago, empty=empty,
    pct_class=pct_class, PERMS=PERMS, PERM_GROUPS=PERM_GROUPS, PERM_KEYS=PERM_KEYS, DIR_PERMS=DIR_PERMS,
    FIELD_TYPES=FIELD_TYPES, VERSION=VERSION, sees_methods=sees_methods, own_only=own_contacts_only, SPECIAL_COLS=SPECIAL_COLS, JOB_TYPES=ai.JOB_TYPES,
    METHOD_LABELS=METHOD_LABELS, METHODS=METHODS, FIELD_SOURCES=FIELD_SOURCES, SOURCE_LABELS=SOURCE_LABELS,
    REJECT_REASONS=REJECT_REASONS, ENRICH_STEPS=ENRICH_STEPS, KIND_LABELS=control.KIND_LABELS,
    job_tab=control.tab_of, job_actions=control.actions, CARD_STYLES=CARD_STYLES, CARD_WIDTHS=CARD_WIDTHS)


# ---------- login & permissions ----------

def _pw_tag(user) -> str:
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def remember_password(request: Request, user):
    """Ties the login to the current password: a new password logs the person out everywhere else."""
    request.session["pw"] = _pw_tag(user)


def current_user(s, request: Request, allow_must_change: bool = False) -> User:
    uid = request.session.get("uid")
    user = s.get(User, uid) if uid else None
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired
    tag = request.session.get("pw")
    if tag is None:   # logged in before v0.6
        remember_password(request, user)
    elif tag != _pw_tag(user):
        request.session.clear()
        raise LoginRequired
    if user.must_change and not allow_must_change:
        raise MustChangePassword
    return user


def require(user, perm, group_id=None):
    if not can(user, perm, group_id):
        raise Forbidden


def require_any(user, perms):
    if not can_any(user, perms):
        raise Forbidden


def flash(request: Request, message: str, error: bool = False):
    request.session["flash"] = [message, error]


def go(url: str):
    return RedirectResponse(url, status_code=303)


def back(request: Request, default: str = "/"):
    ref = request.headers.get("referer") or ""
    host = request.headers.get("host") or ""
    return go(ref if host and f"//{host}/" in ref else default)


# ---------- directories & visibility ----------

def all_groups(s):
    return s.scalars(select(Group).order_by(Group.position, Group.id)).all()


def view_groups(s, user):
    return [g for g in all_groups(s) if can(user, "view", g.id)]


def visible_records_clause(user, groups):
    """SQL condition: contacts this user may see (accepted ones; only their own when set so)."""
    if sees_all_groups(user):
        cond = Record.accepted_at.is_not(None)
    else:
        ids = [g.id for g in groups] or [-1]
        cond = Record.id.in_(select(Membership.record_id).where(Membership.group_id.in_(ids)))
    if own_contacts_only(user):
        cond = and_(cond, Record.found_by == user.id)
    return cond


def own_clause(user):
    """Extra condition for people who only see their own contacts (True for everyone else)."""
    return Record.found_by == user.id if own_contacts_only(user) else true()


def inbox_clause(user, groups):
    if sees_all_groups(user):
        cond = InboxItem.status.is_not(None)
    else:
        ids = [g.id for g in groups] or [-1]
        cond = InboxItem.group_id.in_(ids)
    if own_contacts_only(user):
        cond = and_(cond, InboxItem.record_id.in_(select(Record.id).where(Record.found_by == user.id)))
    return cond


def jobs_clause(user):
    if can(user, "requests_all"):
        return Job.id.is_not(None)
    if own_contacts_only(user):   # people who only see their own contacts only see their own requests
        return Job.user_id == user.id
    if sees_all_groups(user):
        return Job.id.is_not(None)
    return or_(Job.group_id.in_(list(user.group_ids) or [-1]), Job.user_id == user.id)


def can_control(user, job) -> bool:
    if can(user, "requests_all"):
        return True
    return bool(can(user, "requests_own") and job.user_id == user.id and job.kind != "night")


def display_for(s, user) -> dict:
    d = {**DISPLAY_DEFAULTS, **(get_setting(s, "display", {}) or {})}
    d.update((user.prefs or {}).get("display") or {})
    return d


def card_cfg(s, user, group=None) -> dict:
    """How short cards look: style A/B/C, width, colour from tags, at most N per row, fill the row.
    With "fill" (default) the width is a minimum and cards stretch evenly to the full width (v0.8)."""
    d = display_for(s, user)
    cfg = {"style": d.get("card_style") or "A", "width": int(d.get("card_width") or 260),
           "tint": bool(d.get("card_tint", True)), "per_row": int(d.get("per_row") or 0),
           "fill": bool(d.get("card_fill", True))}
    for k, v in ((group.card or {}) if group is not None else {}).items():
        if v not in (None, ""):
            cfg[k] = v
    cfg["style"] = cfg["style"] if cfg["style"] in CARD_STYLES else "A"
    cfg["width"] = min(520, max(180, int(cfg.get("width") or 260)))
    return cfg


def card_fields(user, group) -> list:
    """The (at most 3) fields shown on a directory's short cards: this person's own choice, else the directory's."""
    if group is None:
        return []
    mine = ((user.prefs or {}).get("cardfields") or {}).get(str(group.id))
    if mine is not None:
        keys = [k for k in mine]
        return [f for k in keys for f in group.fields if f.key == k][:3]
    return [f for f in group.fields if f.card and f.key not in ("city", "country")][:3]


def page_style(d: dict) -> str:
    if d["mode"] == "full":
        return "--wrap-max:none;--wrap-w:100%"
    if d["mode"] == "pct":
        pct = min(100, max(50, int(d.get("pct") or 90)))
        return f"--wrap-max:none;--wrap-w:{pct}%"
    return f"--wrap-max:{min(3000, max(800, int(d.get('px') or 1280)))}px;--wrap-w:100%"


def nav_data(s, user) -> dict:
    groups = view_groups(s, user)
    inbox_n = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.status == "new",
                                                            inbox_clause(user, groups))) if can(user, "review") or can(user, "view") else 0
    contacts_n = s.scalar(select(func.count(Record.id)).where(visible_records_clause(user, groups)))
    running = s.scalar(select(func.count(Job.id)).where(
        Job.deleted_at.is_(None), Job.status.in_(list(control.RUNNING | control.WAITING)), jobs_clause(user)))
    return {"nav_groups": groups, "inbox_n": inbox_n or 0, "contacts_n": contacts_n or 0,
            "running_n": running or 0, "views": (user.prefs or {}).get("views") or [],
            "dir_labels": {g.id: g.name for g in groups}}


def theme_for(s, user) -> tuple[str, str]:
    """(css, font link) of the theme this person sees."""
    cfg = {"default": "classic", "allow_personal": True, "follow_dark": False, **(get_setting(s, "theme", {}) or {})}
    saved = get_setting(s, "themes", []) or []
    mine = (user.prefs or {}).get("theme") if user else None
    tid = mine if mine and (cfg["allow_personal"] or can(user, "display_all")) else cfg["default"]
    t = TH.get(saved, tid)
    dark = TH.BUILTIN["dark"] if cfg["follow_dark"] and not TH.is_dark(t) and not mine else None
    return TH.css(t, dark), TH.font_url(t, dark)


def render(request: Request, s, user, name: str, **ctx):
    for key, default in (("sel_group", None), ("q", ""), ("active_nav", None), ("group", None), ("help", "")):
        ctx.setdefault(key, default)
    d = display_for(s, user)
    groups = all_groups(s)
    theme_css, theme_font = theme_for(s, user)
    return templates.TemplateResponse(request, name, {
        "theme_css": theme_css, "theme_font": theme_font,
        "user": user,
        "req_groups": [g for g in groups if can(user, "request", g.id)],
        "add_groups": [g for g in groups if can(user, "add_contacts", g.id)],
        "flash": request.session.pop("flash", None),
        "display": d,
        "page_style": page_style(d),
        "path": request.url.path,
        **nav_data(s, user),
        **ctx,
    })


def last_night(s):
    run = s.scalar(select(NightRun).order_by(NightRun.id.desc()).limit(1))
    if run and run.started_at and datetime.utcnow() - run.started_at < timedelta(hours=36):
        return run
    return None


# ---------- starting requests ----------

def start_job(s, user, kind: str, query: str, group_id: int | None, record_id: int | None = None,
              params: dict | None = None):
    job = Job(query=query, group_id=group_id, kind=kind, user_id=user.id, record_id=record_id, stats={},
              params=params or {})
    s.add(job)
    s.commit()
    control.enqueue_job(job)
    return job


def keyword_blocked(s, text: str, group_id: int | None):
    """(blocked_entry, similar_entries) for a keyword about to be searched."""
    return control.rejected_entry(s, text, group_id), control.similar_rejected(s, text, group_id)


def record_fields_map(s, records, group=None) -> dict:
    """record id -> (fields, filled, total) for completeness bars."""
    from ..contacts import fields_for
    out = {}
    if group is not None:
        fields = list(group.fields)
        for r in records:
            f, t = completeness_of(r, fields)
            out[r.id] = (fields, f, t)
        return out
    gids_by_rec: dict = {}
    if records:
        for rid, gid in s.execute(select(Membership.record_id, Membership.group_id)
                                  .where(Membership.record_id.in_([r.id for r in records]))).all():
            gids_by_rec.setdefault(rid, []).append(gid)
    cache: dict = {}
    for r in records:
        key = tuple(sorted(gids_by_rec.get(r.id, [])))
        if key not in cache:
            cache[key] = fields_for(s, r) if not key else _union_fields(s, key)
        fields = cache[key]
        f, t = completeness_of(r, fields)
        out[r.id] = (fields, f, t)
    return out


def _union_fields(s, gids):
    out, seen = [], set()
    for gid in gids:
        g = s.get(Group, gid)
        for f in (g.fields if g else []):
            if f.key not in seen:
                seen.add(f.key)
                out.append(f)
    return out


def memberships_map(s, records) -> dict:
    """record id -> [group names]"""
    out: dict = {}
    if not records:
        return out
    names = {g.id: g.name for g in all_groups(s)}
    for rid, gid in s.execute(select(Membership.record_id, Membership.group_id)
                              .where(Membership.record_id.in_([r.id for r in records]))).all():
        out.setdefault(rid, []).append(names.get(gid, ""))
    return out
