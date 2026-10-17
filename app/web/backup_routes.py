"""Settings → Backups: automatic nightly backups, Back Up Now, download. Restoring is a server command."""
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from .. import backups as B
from ..db import SessionLocal, set_setting
from .common import all_groups, current_user, flash, go, render, require

router = APIRouter()


@router.get("/settings/backups", response_class=HTMLResponse)
def backups_page(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "backups")
        return render(request, s, user, "backups.html", active_nav="backups", help="backups", all=all_groups(s),
                      cfg=B.settings(s), st=B.status(s), files=B.files(), folder_ok=B.folder_ok(),
                      pending=B.pending(s), warning=B.warning(s), last_ok=B.last_ok(s), size_text=B.size_text)


@router.post("/settings/backups")
async def backups_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "backups")
        if form.get("action") == "now":
            B.request_now(s)
            s.commit()
            flash(request, "Backup asked for. It starts within a minute; reload this page to see it in the list.")
            return go("/settings/backups")
        at = str(form.get("time") or "02:30")
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", at):
            at = "02:30"
        try:
            keep = min(365, max(1, int(form.get("keep_days") or 14)))
        except ValueError:
            keep = 14
        set_setting(s, "backups", {"enabled": form.get("enabled") == "on", "time": at, "keep_days": keep})
        s.commit()
        flash(request, "Backup settings saved.")
    return go("/settings/backups")


@router.get("/settings/backups/file/{name}")
def backup_download(request: Request, name: str):
    with SessionLocal() as s:
        user = current_user(s, request)
        require(user, "backups")
    path = B.safe_path(name)
    if not path:
        return go("/settings/backups")
    return FileResponse(path, filename=name, media_type="application/octet-stream")
