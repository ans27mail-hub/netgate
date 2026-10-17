"""End-to-end test of NetGate v0.7 on a database made by v0.6 (run tests/test_v06.py first, or use a copy of a v0.6
database with its sample data: users admin / worker1 / viewer1 / dev1, password secret123).
Checks: tags, card styles, short-card fields, themes, what each person sees (own contacts / directories,
Existing Contacts, See search methods, enrich others), debug page, Running Jobs, backups (with the real
backup/run.sh), the Developer Handbook and Title Case labels."""
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import handbook, jobs, tags as TG
from app.db import (AppLog, ExistingHit, Field, Group, InboxItem, Job, JobTrace, Membership, Record, RecordTag, Role,
                    SessionLocal, Setting, Tag, User, get_setting, set_setting)

fails = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


app = __import__("app.main", fromlist=["app"]).app


def client(name, password="secret123"):
    cl = TestClient(app)
    cl.__enter__()
    cl.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    return cl


c = client("admin")

# ---------- upgrade ----------
with SessionLocal() as s:
    check(s.get(Setting, "v07_upgraded") is not None, "v0.7 upgrade ran")
    tags = TG.all_tags(s)
    check([t.name for t in tags][:3] == ["Hot lead", "Customer", "Sample sent"] and len(tags) == 6, "six starting tags")
    groups = {g.name: g for g in s.scalars(select(Group)).all()}
    man, mat, buy = groups["Manufacturers"], groups["Materials"], groups["Buyers & brands"]
    admin = s.scalar(select(User).where(User.username == "admin"))
    check(all(g.owner_id == admin.id for g in groups.values()), "existing directories belong to the first admin")
    check(s.scalar(select(func.count(Record.id)).where(Record.found_by.is_not(None))) > 0, "first finder filled in")
    roles = {r.name: r for r in s.scalars(select(Role)).all()}
    check("enrich_others" in roles["Researcher"].perm_set and "see_methods" not in roles["Researcher"].perm_set,
          "Researcher: may enrich others' contacts, doesn't see methods")
    check({"see_methods", "manage_tags"} <= roles["Manager"].perm_set, "Manager sees methods and manages tags")
    kappa = s.scalar(select(Record).where(Record.title == "Kappa Leathers"))
    kid = kappa.id
    hot, smp, cus = tags[0], tags[2], tags[1]

# ---------- tags ----------
r = c.get("/settings/tags")
check(r.status_code == 200 and "Hot lead" in r.text and "+ New Tag" in r.text, "Settings → Tags")
r = c.post("/settings/tags/new", data={"name": "VIP", "color": "#6d4bc4", "description": "Top buyer", "where": "all",
                                       "color_card": "on"})
with SessionLocal() as s:
    vip = s.scalar(select(Tag).where(Tag.name == "VIP"))
check(vip and vip.color == "#6d4bc4" and vip.position == 6, "new tag created at the end")
c.post(f"/settings/tags/{vip.id}", data={"name": "VIP", "custom": "#123456", "where": "some", "groups": [str(buy.id)]})
with SessionLocal() as s:
    vip = s.get(Tag, vip.id)
check(vip.color == "#123456" and not vip.all_groups and vip.group_ids == [buy.id], "own colour, limited to a directory")
c.post(f"/settings/tags/{vip.id}", data={"action": "up"})
with SessionLocal() as s:
    check([t.name for t in TG.all_tags(s)][-2:] == ["VIP", "Do not contact"], "order: move up")
r = c.post(f"/records/{kid}/tags", data={"tag_ids": [str(smp.id), str(hot.id), str(vip.id)], "from": str(man.id)})
check(r.status_code == 200 and "Sample sent" in r.text and "Hot lead" in r.text, "tags set on the big card")
with SessionLocal() as s:
    have = set(s.scalars(select(RecordTag.tag_id).where(RecordTag.record_id == kid)).all())
    rec = s.get(Record, kid)
check(have == {hot.id, smp.id} and any("Tagged Hot lead by admin" in h["text"] for h in rec.history),
      "tag limited to another directory isn't added; history notes tagging")
r = c.get(f"/d/{man.id}?view=grid")
check('class="tagbar-mark" style="--tc:#c43d3d"' in r.text, "card shows the tag mark in its colour")
bg = TG.soft("#c43d3d", 0.07)
check(f"background:{bg}" in r.text, "card coloured from its strongest tag (Hot lead)")
check('class="tagbar"' in r.text and "Hot lead <span class=\"n\">1</span>" in r.text, "tag bar with counts")
r = c.get(f"/d/{man.id}?tag={hot.id}")
check("Kappa Leathers" in r.text and "Theta Gear" not in r.text and "Tag:</span> Hot lead" in r.text, "filter by tag")
r = c.get(f"/d/{man.id}?sort=tag&view=list")
names = re.findall(r"<strong>([^<]+)</strong>", r.text)
check(names and names[0] == "Kappa Leathers", "sort by Tag Order puts tagged contacts first")
r = c.post(f"/records/{kid}/tags", data={"remove": str(smp.id)})
with SessionLocal() as s:
    ids = [r_.id for r_ in s.scalars(select(Record).join(Membership, Membership.record_id == Record.id)
                                     .where(Membership.group_id == man.id).order_by(Record.id)).all()]
    check(s.scalar(select(func.count()).select_from(RecordTag).where(RecordTag.record_id == kid,
                                                                     RecordTag.tag_id == smp.id)) == 0, "× takes a tag off")
r = c.post("/records/tags-bulk", data={"ids": [str(i) for i in ids[:3]], "tag_id": str(cus.id), "action": "add"},
           headers={"referer": f"http://testserver/d/{man.id}"})
check("added to 3 contacts" in r.text, "bulk Add Tag")
r = c.post("/records/tags-bulk", data={"ids": [str(i) for i in ids[:3]], "tag_id": str(cus.id), "action": "remove"},
           headers={"referer": f"http://testserver/d/{man.id}"})
check("removed from 3 contacts" in r.text, "bulk Remove Tag")
c.post(f"/records/{kid}/tags", data={"tag_ids": [str(smp.id), str(hot.id)]})
r = c.post(f"/settings/tags/{smp.id}", data={"action": "merge", "into": str(hot.id)})
with SessionLocal() as s:
    check(s.get(Tag, smp.id) is None and s.scalar(select(func.count()).select_from(RecordTag)
                                                  .where(RecordTag.record_id == kid)) == 1, "merge moves contacts and removes the tag")
r = c.post(f"/settings/tags/{vip.id}", data={"action": "delete"})
with SessionLocal() as s:
    check(s.get(Tag, vip.id) is None and s.get(Record, kid) is not None, "delete tag keeps contacts")
w = client("worker1")
check(w.get("/settings/tags").status_code == 403, "Researcher can't manage tags")
check(w.post(f"/records/{kid}/tags", data={"tag_ids": [str(hot.id)]}).status_code == 403,
      "Researcher (no Edit contacts) can't tag")

# ---------- card styles & short-card fields ----------
c.post(f"/settings/directories/{man.id}", data={"section": "cards", "card_style": "C", "card_width": "320",
                                                "card_tint": "off"})
with SessionLocal() as s:
    check(s.get(Group, man.id).card == {"style": "C", "width": 320, "tint": False}, "directory card settings saved")
r = c.get(f"/d/{man.id}?view=grid")
check("grid cards style-c" in r.text and "--cardw:320px" in r.text and f"background:{bg}" not in r.text,
      "directory uses style C, fixed 320 px, no tint")
r = c.get(f"/d/{mat.id}?view=grid")
check("grid cards style-a" in r.text and "--cardw:260px" in r.text, "other directory keeps the default A / 260 px")
c.post("/settings/display", data={"mode": "fixed", "px": "1280", "pct": "90", "view": "grid", "per_row": "3",
                                  "card_style": "B", "card_width": "240", "card_tint": "on", "scope": "everyone"})
r = c.get(f"/d/{mat.id}?view=grid")
check("style-b" in r.text and "--cardw:240px;max-width:744px" in r.text, "Display defaults: style B, 240 px, at most 3 per row")
r = c.get(f"/records/{kid}/open?from={man.id}")
check("Short Card Shows…" in r.text and 'name="scope" value="dir"' in r.text, "Short Card Shows panel on the big card")
r = c.post(f"/records/{kid}/cardfields", data={"group_id": str(man.id), "fields": ["website", "employees"], "scope": "me"})
with SessionLocal() as s:
    check((s.scalar(select(User).where(User.username == "admin")).prefs or {}).get("cardfields", {}).get(str(man.id))
          == ["website", "employees"], "short card fields only for me")
r = c.post(f"/records/{kid}/cardfields", data={"group_id": str(man.id), "fields": ["products"], "scope": "dir"})
with SessionLocal() as s:
    flags = {f.key: f.card for f in s.get(Group, man.id).fields}
    check(flags.get("products") and not flags.get("website") and not flags.get("employees"),
          "short card fields for every card in the directory")
check(w.post(f"/records/{kid}/cardfields", data={"group_id": str(man.id), "fields": ["products"],
                                                 "scope": "dir"}).status_code == 403,
      "only people who manage directories change it for everyone")

# ---------- themes ----------
r = c.get("/settings/themes")
check(r.status_code == 200 and "NetGate Classic" in r.text and "Dark" in r.text, "Settings → Themes")
r = c.post("/settings/themes", data={"action": "copy", "id": "classic"}, follow_redirects=False)
tid = r.headers["location"].split("edit=")[1]
r = c.post("/settings/themes", data={"id": tid, "name": "Warm sand", "c_side": "#3a2e22", "c_side_text": "#f3e9dc",
                                     "c_bg": "#f7f1e8", "c_card": "#ffffff", "c_line": "#e2d6c6", "c_ink": "#2b2118",
                                     "c_muted": "#6e5f50", "c_accent": "#b5562b", "font": "IBM Plex Sans",
                                     "corners": "slight", "spacing": "compact", "action": "save"})
check("Theme saved" in r.text and "Warm sand" in r.text, "own theme saved")
r = c.post("/settings/themes", data={"action": "use", "id": tid})
r = c.get("/")
check("--accent:#b5562b" in r.text and "IBM+Plex+Sans" in r.text and "--fs:14px" in r.text and "--radius:8px" in r.text,
      "theme for everyone applied (colours, font, spacing, corners)")
check("--accent:#b5562b" in w.get("/").text, "everyone sees it")
w.post("/settings/themes", data={"action": "mine", "id": "dark"}, headers={"referer": "http://testserver/settings/display"})
check("--bg:#1b1e24" in w.get("/").text and "--accent:#b5562b" in c.get("/").text, "a person can pick their own theme")
r = c.post("/settings/themes", data={"id": tid, "name": "Warm sand", "c_ink": "#f0f0f0", "c_bg": "#ffffff",
                                     "action": "save"})
check("hard to read" in r.text, "readability warning for pale text")
c.post("/settings/themes", data={"action": "settings", "default": "classic", "allow_personal": "on", "follow_dark": "on"})
check("@media (prefers-color-scheme: dark)" in c.get("/").text, "follow the computer's dark mode")
c.post("/settings/themes", data={"action": "settings", "default": "classic", "allow_personal": ""})
check("--bg:#1b1e24" not in w.get("/").text, "when personal themes are off, everyone gets the theme for everyone")
r = c.post("/settings/themes", data={"action": "delete", "id": tid})
check("deleted" in r.text and "Warm sand" not in c.get("/settings/themes").text, "delete a theme")
check(w.get("/settings/themes").status_code == 403, "Researcher can't change themes")

# ---------- what each person sees ----------
with SessionLocal() as s:
    researcher = s.scalar(select(Role).where(Role.name == "Researcher"))
c.post("/settings/users/new", data={"username": "surfer1", "password": "secret123", "role_id": researcher.id,
                                    "active": "on", "access": "some", "groups": [str(man.id), str(buy.id)],
                                    "contacts_scope": "own", "existing_view": "fields",
                                    "existing_fields": ["products"]})
with SessionLocal() as s:
    surfer = s.scalar(select(User).where(User.username == "surfer1"))
    check(surfer.contacts_scope == "own" and surfer.dir_scope == "some" and surfer.existing_fields == ["products"],
          "new user: only own contacts, selected directories, chosen fields for existing contacts")
    sid = surfer.id
    job = Job(query="glove makers sialkot", group_id=man.id, kind="request", user_id=sid, status="running", stats={},
              params={})
    s.add(job)
    s.commit()
    ctx = jobs.Ctx(job.id, "discover")
    g = s.get(Group, man.id)
    res_new = jobs.save_found(s, ctx, g, name="Surfer Gloves Works", values={"city": "Sialkot", "country": "Pakistan"},
                              sources={}, method="web", query="glove makers sialkot", page_url="http://dir.test/list")
    res_old = jobs.save_found(s, ctx, g, name="Kappa Leathers", values={"products": ["leather gloves"]},
                              sources={}, method="web", query="glove makers sialkot", page_url="http://dir.test/list")
    s.commit()
    new_rec = s.scalar(select(Record).where(Record.title == "Surfer Gloves Works"))
    old_rec = s.get(Record, kid)
    check(res_new == "saved" and new_rec.found_by == sid, "a new company found by surfer1 is theirs (first finder)")
    check(old_rec.found_by != sid and s.get(ExistingHit, (sid, kid, man.id)) is not None,
          "an existing company keeps its first finder and is listed as an Existing Contact")
    check(not any("found again" in (h["text"] or "").lower() for h in old_rec.history), "no “found again” history")
    item = s.scalar(select(InboxItem).where(InboxItem.record_id == new_rec.id))
    from app import contacts as C
    C.accept(s, item, s.scalar(select(User).where(User.username == "admin")))
    s.commit()
    nid = new_rec.id
u = client("surfer1")
r = u.get("/contacts")
check("Surfer Gloves Works" in r.text and "Theta Gear" not in r.text, "surfer1 sees only their own contacts")
r = u.get(f"/d/{man.id}")
check("Surfer Gloves Works" in r.text and "Kappa Leathers" not in r.text, "…also inside a directory")
check(u.get(f"/d/{mat.id}").status_code == 403, "…and only their directories")
r = u.get(f"/d/{man.id}?tab=existing")
check("Kappa Leathers" in r.text and "surfer1" in r.text and "limited view" in r.text, "Existing Contacts tab")
r = u.get(f"/records/{kid}/open")
check(r.status_code == 200 and "Existing Contact" in r.text and "Products" in r.text and "Website" not in r.text
      and ">Edit<" not in r.text and "+ Tag" not in r.text, "existing contact opens with only the allowed fields")
check("Enrich Now" in r.text, "may enrich others' contacts (role permission)")
u.post(f"/records/{kid}/enrich")
with SessionLocal() as s:
    surfer = s.get(User, sid)
    surfer.removed_perms = "enrich_others"
    s.commit()
r = u.get(f"/records/{kid}/open")
check("Enrich Now" not in r.text, "without the permission there is no Enrich on others' contacts")
check(u.post(f"/records/{kid}/enrich").status_code == 403, "…and enriching it is refused")
check(u.post(f"/records/{nid}/enrich").status_code in (200, 303), "own contact can still be enriched")
check(u.post(f"/records/{kid}/edit", data={"title": "x"}).status_code == 403, "existing contact can't be edited")
check(u.get(f"/records/{ids[1]}/open").status_code == 403, "other contacts can't be opened")
r = u.get("/inbox")
check("Kappa Leathers" not in r.text, "Inbox shows only their own finds")
r = u.get("/")
check("Surfer Gloves" in r.text or r.status_code == 200, "Dashboard works for surfer1")
# own directories
c.post("/settings/users/new", data={"username": "owner1", "password": "secret123", "role_id": researcher.id,
                                    "active": "on", "access": "own", "contacts_scope": "all"})
with SessionLocal() as s:
    o1 = s.scalar(select(User).where(User.username == "owner1"))
    s.get(Group, mat.id).owner_id = o1.id
    s.commit()
    check(o1.dir_scope == "own" and not o1.all_groups, "user with only their own directories")
o = client("owner1")
r = o.get("/directories")
check(f'href="/d/{mat.id}"' in r.text and f'href="/d/{man.id}"' not in r.text, "they see only the directory they own")
# search methods
r = u.get(f"/d/{man.id}")
check('class="mbadge' not in r.text and 'id="ask-methods" hidden' in r.text, "no search methods for a Researcher")
r = c.get(f"/d/{man.id}")
check('class="mbadge' in r.text and 'id="ask-methods" hidden' not in r.text, "admin sees the methods")
u.post("/jobs", data={"query": "biker gloves", "group_id": str(man.id), "methods": ["web"]})
with SessionLocal() as s:
    j = s.scalar(select(Job).where(Job.query == "biker gloves"))
    check(j and not (j.params or {}).get("methods"), "their searches use all the directory's methods")
# user page shows the settings
r = c.get(f"/settings/users/{sid}")
check("What This Person Sees" in r.text and 'value="own" checked' in r.text, "user page: What This Person Sees")

# ---------- debug page ----------
with SessionLocal() as s:
    dj = s.scalar(select(Job).where(Job.kind.in_(["request", "keyword"]), Job.status == "done").order_by(Job.id))
    s.add(JobTrace(job_id=dj.id, kind="note", url="", data={"x": 1}))
    s.commit()
    djid = dj.id
r = c.get(f"/requests/{djid}/debug")
check("← Back to Requests" in r.text and "Run Again" in r.text and "Clear Debug Notes" in r.text, "debug page actions")
r = c.post(f"/requests/{djid}/debug/clear")
with SessionLocal() as s:
    check(s.scalar(select(func.count(JobTrace.id)).where(JobTrace.job_id == djid)) == 0
          and s.get(Job, djid) is not None, "Clear Debug Notes keeps the request")

# ---------- Running Jobs ----------
with SessionLocal() as s:
    rj = s.get(Job, job.id)
    rj.stats, rj.message, rj.status = {"page_no": 3, "pages_total": 12, "saved": 5}, "Page 3 of 12: http://dir.test/list", "crawling"
    s.add(Job(query="waiting keyword", group_id=man.id, kind="keyword", user_id=admin.id, status="queued", stats={},
              params={}))
    s.commit()
r = c.get("/dashboard/jobs")
check("glove makers sialkot" in r.text and "width:25%" in r.text and "5 new" in r.text and "Pause" in r.text,
      "Running Jobs: progress, results, Pause")
check("waiting keyword" in r.text and "Waiting" in r.text, "Running Jobs: waiting list")
check('id="runjobs"' in c.get("/").text, "Running Jobs panel on the Dashboard")
r = u.get("/dashboard/jobs")
check("glove makers sialkot" in r.text and "waiting keyword" not in r.text, "surfer1 sees only their own jobs")

# ---------- backups ----------
with SessionLocal() as s:
    for k in ("backups.status", "backups.request"):
        row = s.get(Setting, k)
        if row:
            s.delete(row)
    s.commit()
check("No backup has been made yet" in c.get("/").text, "Dashboard warns: no backup yet")
check("No backup" not in w.get("/").text, "…only to people with Backups")
r = c.post("/settings/backups", data={"enabled": "on", "time": "02:30", "keep_days": "10"})
with SessionLocal() as s:
    check(get_setting(s, "backups") == {"enabled": True, "time": "02:30", "keep_days": 10}, "backup settings saved")
c.post("/settings/backups", data={"action": "now"})
check("Backup Asked For" in c.get("/settings/backups").text, "Back Up Now asks the backup service")
db = urlparse(os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql"))
bdir = os.environ.get("BACKUP_DIR", "/backups")
env = {**os.environ, "PGHOST": db.hostname, "PGPORT": str(db.port or 5432), "PGUSER": db.username or "postgres",
       "PGDATABASE": db.path.lstrip("/"), "BACKUP_DIR": bdir, "RUN_ONCE": "1"}
out = subprocess.run(["sh", os.path.join(ROOT, "backup", "run.sh")], env=env, capture_output=True, text=True, timeout=120)
with SessionLocal() as s:
    st = get_setting(s, "backups.status") or {}
check(st.get("last_ok_at") and st.get("last_file", "").endswith(".dump"), "backup service made a backup: " + out.stdout.strip()[-80:])
r = c.get("/settings/backups")
check(st["last_file"] in r.text and "Download" in r.text and "Backup Asked For" not in r.text, "backup listed")
r = c.get(f"/settings/backups/file/{st['last_file']}")
check(r.status_code == 200 and r.content[:5] == b"PGDMP", "backup downloads (pg_dump file)")
check(c.get("/settings/backups/file/..%2F..%2Fetc%2Fpasswd").status_code in (200, 303, 404) and
      b"root:" not in c.get("/settings/backups/file/..%2F..%2Fetc%2Fpasswd").content, "no files outside the folder")
check("No backup has been made" not in c.get("/").text, "warning gone after a backup")
check(w.get("/settings/backups").status_code == 403, "Researcher can't open Backups")

# ---------- Handbook ----------
check(handbook.missing_features() == [], "every feature has a Handbook page")
for p in handbook.written():
    if not p["updated"]:
        check(False, f"Handbook page {p['slug']} says when it was updated")
r = c.get("/dev/handbook")
check(r.status_code == 200 and "Developer Handbook" in r.text and "Made From the Code" in r.text, "Handbook opens")
check("existing_hits" in c.get("/dev/handbook/auto-database").text, "automatic page: database tables")
check("see_methods" in c.get("/dev/handbook/auto-permissions").text, "automatic page: permissions")
check("DISCOVER_PROMPT" in c.get("/dev/handbook/auto-prompts").text, "automatic page: AI prompts")
check("/dev/handbook/{slug}" in c.get("/dev/handbook/auto-routes").text, "automatic page: addresses")
check("backup" in c.get("/dev/handbook/auto-versions").text, "automatic page: containers")
check("Backups" in c.get("/dev/handbook?q=backup").text, "Handbook search")
d = client("dev1")
check(d.get("/dev/handbook").status_code == 200 and w.get("/dev/handbook").status_code == 403,
      "Handbook: Developer yes, Researcher no")
r = c.get("/dev/handbook/feature-tags")
check("Last updated in v0.7" in r.text, "feature page shows its version")

# ---------- Title Case & help ----------
r = c.get(f"/d/{man.id}")
for label in ("All Contacts", "Run Discovery", "Existing Contacts", "Directory Settings", "Save View", "+ Add Filter"):
    check(label in r.text, f"Title Case: {label}")
r = c.get("/")
for label in ("Needs Attention", "Running Jobs", "Quick Actions", "Recent Activity"):
    check(label in r.text, f"Title Case: {label}")
for url in ["/", "/directories", f"/d/{man.id}", f"/d/{man.id}?view=list", f"/d/{man.id}?tab=existing", "/contacts",
            "/contacts?view=list", "/inbox", "/requests", "/settings/tags", "/settings/themes", "/settings/backups",
            "/settings/display", f"/settings/directories/{man.id}", "/settings/users", f"/settings/users/{sid}",
            "/settings/roles", "/help", "/help/tags", "/help/themes", "/help/backups", "/help/whats-new", "/dev",
            "/dev/handbook/overview", "/dev/handbook/auto-settings"]:
    rr = c.get(url)
    check(rr.status_code == 200 and "Something went wrong" not in rr.text, f"GET {url}")
with SessionLocal() as s:
    errs = s.scalars(select(AppLog).where(AppLog.level == "error")).all()
    check(not errs, "no errors in the log" + (": " + errs[0].message if errs else ""))

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
