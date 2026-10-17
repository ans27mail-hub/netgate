"""Backups of the whole database. The `backup` container (postgres:16 tools) makes them; this module reads its
settings and results, which both sides keep in app_settings:
  backups          {"enabled", "time" "HH:MM", "keep_days"}   (set on Settings → Backups)
  backups.request  {"at": ...}                                (Back Up Now; the container picks it up within a minute)
  backups.status   {"last_ok_at", "last_file", "last_size", "last_error", "last_try_at"}  (written by the container)
Files: <BACKUP_DIR>/netgate-YYYYMMDD-HHMM.dump (pg_dump custom format). Restore with `netgate restore` on the server."""
import os
from datetime import datetime, timedelta

from .db import get_setting, set_setting

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/backups")
DEFAULTS = {"enabled": True, "time": "02:30", "keep_days": 14}


def settings(s) -> dict:
    return {**DEFAULTS, **(get_setting(s, "backups", {}) or {})}


def status(s) -> dict:
    return get_setting(s, "backups.status", {}) or {}


def request_now(s):
    set_setting(s, "backups.request", {"at": datetime.utcnow().isoformat(timespec="seconds")})


def pending(s) -> bool:
    req = get_setting(s, "backups.request", {}) or {}
    st = status(s)
    return bool(req.get("at") and (not st.get("last_try_at") or st["last_try_at"] < req["at"]))


def files() -> list[dict]:
    """Backup files, newest first."""
    out = []
    try:
        names = os.listdir(BACKUP_DIR)
    except OSError:
        return out
    for n in names:
        if n.startswith("netgate-") and n.endswith(".dump"):
            p = os.path.join(BACKUP_DIR, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append({"name": n, "size": st.st_size, "at": datetime.utcfromtimestamp(st.st_mtime)})
    return sorted(out, key=lambda f: f["name"], reverse=True)


def folder_ok() -> bool:
    return os.path.isdir(BACKUP_DIR)


def safe_path(name: str) -> str | None:
    if not (name.startswith("netgate-") and name.endswith(".dump")) or "/" in name or ".." in name:
        return None
    p = os.path.join(BACKUP_DIR, name)
    return p if os.path.isfile(p) else None


def last_ok(s) -> datetime | None:
    v = status(s).get("last_ok_at")
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def warning(s) -> str:
    """Plain-English warning for the Dashboard, or ''."""
    cfg = settings(s)
    if not cfg.get("enabled"):
        return "Automatic backups are switched off"
    ok = last_ok(s)
    if not ok:
        return "No backup has been made yet"
    if datetime.utcnow() - ok > timedelta(days=2):
        return f"The last backup is {(datetime.utcnow() - ok).days} days old"
    return ""


def size_text(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} bytes"
