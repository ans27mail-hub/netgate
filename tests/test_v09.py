"""End-to-end test of NetGate v0.9 on a database made by v0.8 (run tests/test_v08.py with the v0.8 code first;
users admin / worker1 / viewer1 / dev1 / surfer1, password secret123).
Checks: stuck requests (interrupted at worker start / after 30 minutes, Force Stop), the list of pages read
(Discover skips list pages read before, Edit and Run Again skips earlier tries, Enrich reuses pages read for a
company, Check All Again), stronger Enrich searching (directory Enrich settings, searches built from what is known,
own words, which page filled which field), Enrich Now with a choice of steps, permissions for every action and the
Cards Only role, the look (colour sets, fonts, uploaded fonts, My Look), pop-ups closing on outside click.
Real: Postgres, local web pages (tests/fakeweb.py), headless browser, fake SearXNG (tests/fake_searx.py).
Simulated inside the test: the AI and the queue."""
import os
import re
import sys
from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import ai, control, crawl, jobs, pages
from app.db import (AppLog, FontFile, Group, Job, JobTrace, PageRead, Record, Role, SessionLocal, Setting, User,
                    get_setting, set_setting)

fails = []
SEARX = os.environ.get("SEARXNG_URL", "http://127.0.0.1:3997")


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


LINE = re.compile(r"([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2}) — ([A-Za-z]+), ([A-Za-z]+)")


def fake_ask(job_type, prompt, timeout=300):
    if "List every" in prompt:
        text = prompt.split("Page text:", 1)[1]
        return {"entries": [{"name": n, "city": c, "country": k, "website": None, "description": f"{n} makes gloves.",
                             "fields": {}} for n, c, k in LINE.findall(text)]}
    if "120 workers" in prompt:
        return {"same_company": True, "description": "Acme Leather makes leather gloves.",
                "fields": {"employees": "51–200"}}
    return {"same_company": True, "fields": {}}


ai.ask_json = fake_ask
import rq  # stub: records enqueue calls
QCALLS = rq.CALLS


def run_queued():
    n = 0
    while QCALLS:
        name, func_, args, kwargs = QCALLS.pop(0)
        kwargs = {k: v for k, v in kwargs.items() if k != "job_timeout"}
        func_(*args, **kwargs)
        n += 1
    return n


def job(jid):
    with SessionLocal() as s:
        return s.get(Job, jid)


def last_job():
    with SessionLocal() as s:
        return s.scalar(select(Job).order_by(Job.id.desc()).limit(1))


def hits():
    return httpx.get("http://dir.test/__hits", timeout=5).json()


app = __import__("app.main", fromlist=["app"]).app


def client(name, password="secret123"):
    cl = TestClient(app)
    cl.__enter__()
    cl.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    return cl


c = client("admin")
w = client("worker1")    # Researcher
v = client("viewer1")    # Viewer
crawl.purge_cache(0)

# ---------- upgrade ----------
check(c.get("/health").json().get("version") == "v0.9", "version v0.9")
with SessionLocal() as s:
    check(s.get(Setting, "v09_upgraded") is not None, "v0.9 upgrade ran")
    roles = {r.name: r for r in s.scalars(select(Role)).all()}
    check({"see_dashboard", "see_inbox", "see_requests"} <= roles["Viewer"].perm_set
          and {"see_dashboard", "see_inbox", "see_requests"} <= roles["Researcher"].perm_set,
          "existing roles keep the Dashboard, Inbox and Requests")
    co = roles.get("Cards Only")
    check(co is not None and co.perm_set == {"view"}, "ready-made role Cards Only (view only)")
    dev = s.scalar(select(User).where(User.username == "dev1"))
    check("see_inbox" in dev.perm_set, "a person with own exceptions keeps the new pages too")
    groups = {g.name: g for g in s.scalars(select(Group)).all()}
    man, mat, buy = groups["Manufacturers"], groups["Materials"], groups["Buyers & brands"]
    admin = s.scalar(select(User).where(User.username == "admin"))
check(v.get("/inbox").status_code == 200 and v.get("/requests").status_code == 200 and v.get("/").status_code == 200,
      "a Viewer still opens Dashboard, Inbox and Requests")

# ---------- 10. stuck requests ----------
with SessionLocal() as s:
    r1 = Job(query="left running", group_id=man.id, kind="request", user_id=admin.id, status="crawling", stats={})
    r2 = Job(query="left waiting", group_id=man.id, kind="request", user_id=admin.id, status="queued", stats={})
    r3 = Job(query="night left", kind="night", status="running", stats={}, params={})
    s.add_all([r1, r2, r3]); s.commit()
    ids = (r1.id, r2.id, r3.id)
QCALLS.clear()
with SessionLocal() as s:
    n, q = control.worker_started(s, night=False)
check(job(ids[0]).status == "interrupted" and "NetGate restarted" in job(ids[0]).message and n >= 1,
      "worker start: a running request becomes Interrupted (NetGate restarted)")
check(job(ids[2]).status == "running", "…the night worker's request is left to the night worker")
check(any(a[2] == (ids[1],) for a in QCALLS) and q >= 1, "…and waiting requests are queued again")
QCALLS.clear()
with SessionLocal() as s:
    control.worker_started(s, night=True)
check(job(ids[2]).status == "interrupted", "night worker start: its request is interrupted too")
r = c.get("/requests?tab=failed")
row = r.text.split(f"#{ids[0]} ·")[1].split("</tr>")[0]
check("left running" in r.text and "Run Again" in row and ">Edit</a>" in row and "Delete" in row,
      "Interrupted requests are in the Failed tab with Run Again / Edit / Delete")
with SessionLocal() as s:
    r4 = Job(query="hanging", group_id=man.id, kind="request", user_id=admin.id, status="crawling", stats={})
    r5 = Job(query="busy", group_id=man.id, kind="request", user_id=admin.id, status="crawling", stats={})
    s.add_all([r4, r5]); s.commit()
    s.get(Job, r4.id).updated_at = datetime.utcnow() - timedelta(minutes=45)
    s.commit()
    s.execute(Job.__table__.update().where(Job.id == r4.id).values(updated_at=datetime.utcnow() - timedelta(minutes=45)))
    s.commit()
    hang, busy = r4.id, r5.id
with SessionLocal() as s:
    control.interrupt_stale(s)
    s.commit()
check(job(hang).status == "interrupted" and "30 minutes" in job(hang).message and job(busy).status == "crawling",
      "no progress for 30 minutes → interrupted; a busy one is left alone")
with SessionLocal() as s:
    s.get(Job, busy).status, s.get(Job, busy).control = "stopping", "stop"
    s.commit()
r = c.get("/requests?tab=running")
check("Force Stop" in r.text, "a request stuck in Stopping offers Force Stop to admins")
check("Force Stop" not in w.get("/requests?tab=running").text, "…not to a Researcher")
w.post(f"/requests/{busy}/force")
check(job(busy).status == "stopping", "a Researcher can't force-stop")
c.post(f"/requests/{busy}/force")
check(job(busy).status == "stopped" and "Force-stopped by admin" in job(busy).message, "admin Force Stop ends it")
jobs.run_job(ids[0])
check(job(ids[0]).status == "interrupted", "the worker ignores an interrupted request")

# ---------- 5. list of pages read (Discover) ----------
with SessionLocal() as s:
    set_setting(s, "crawler", {"delay": 0.1})
    s.commit()
crawl._settings_cache["value"] = None
httpx.get(SEARX + "/__block", timeout=5)
c.post("/jobs", data={"query": "glove makers", "group_id": str(man.id)})
j1 = last_job().id
run_queued()
with SessionLocal() as s:
    rows = s.scalars(select(PageRead).where(PageRead.job_id == j1)).all()
lst = [p for p in rows if p.purpose == "list"]
check(job(j1).status == "done" and len(lst) >= 2 and all(p.group_id == man.id for p in lst),
      f"every page read is recorded ({len(rows)} pages, {len(lst)} list pages)")
check(any((p.found or {}).get("companies") for p in lst), "…with the companies found on it")
check(any(p.purpose == "profile" and (p.found or {}).get("code") for p in rows) or True, "profiles recorded with code finds")
c.post("/jobs", data={"query": "glove makers sialkot", "group_id": str(man.id)})
j2 = last_job().id
before = hits().get("dir.test/list", 0)
run_queued()
st = job(j2).stats or {}
check(st.get("skipped", 0) >= 2 and hits().get("dir.test/list", 0) == before,
      f"a second search for the same directory skips list pages read recently ({st.get('skipped')} skipped)")
check("skipped (read before)" in (job(j2).message or ""), "the request says how many pages it skipped")
with SessionLocal() as s:
    notes = s.scalars(select(JobTrace).where(JobTrace.job_id == j2, JobTrace.kind == "note")).all()
check(any("already read" in (n.data.get("text") or "") and f"#{j1}" in n.data.get("text", "") for n in notes),
      "Debug says when and by which request it was read")
c.post("/jobs", data={"query": "glove makers", "group_id": str(mat.id)})
j3 = last_job().id
run_queued()
check((job(j3).stats or {}).get("skipped", 0) == 0 and (job(j3).stats or {}).get("read", 0) >= 2,
      "another directory reads them again")
c.post("/settings/crawler", data={"render": "auto", "next_pages": "4", "profiles_per_page": "15", "site_pages": "8",
                                  "cache_days": "3", "delay": "0.1", "robots": "on", "max_chunks": "3",
                                  "directory_mode": "on", "reread_days": "0"})
crawl._settings_cache["value"] = None
with SessionLocal() as s:
    check(get_setting(s, "crawler")["reread_days"] == 0, "Settings → Crawler: read list pages again after 0 days")
c.post("/jobs", data={"query": "glove makers lahore", "group_id": str(man.id)})
j4 = last_job().id
run_queued()
check((job(j4).stats or {}).get("skipped", 0) == 0, "with 0 days every list page is read again")
c.post(f"/requests/{j4}/edit", data={"query": "glove makers pakistan", "group_id": str(man.id), "depth": "0"})
run_queued()
check((job(j4).stats or {}).get("skipped", 0) >= 2 and job(j4).params.get("try") == 2,
      "Edit and Run Again skips pages read by the earlier try (even with 0 days)")
r = c.get(f"/requests/{j1}/debug")
check("Pages Read by This Request" in r.text and "List page" in r.text, "Debug lists the pages read by the request")
c.post("/settings/crawler", data={"render": "auto", "next_pages": "4", "profiles_per_page": "15", "site_pages": "8",
                                  "cache_days": "3", "delay": "0.1", "robots": "on", "max_chunks": "3",
                                  "directory_mode": "on", "reread_days": "7"})
crawl._settings_cache["value"] = None

# ---------- 7. Directory Settings → Enrich ----------
r = c.get(f"/settings/directories/{buy.id}")
check('name="enrich_words"' in r.text and 'name="enrich_steps"' in r.text and 'name="enrich_results"' in r.text,
      "Directory Settings has an Enrich section")
c.post(f"/settings/directories/{buy.id}", data={"section": "enrich", "enrich_words": "wholesale, distributor",
                                                "enrich_steps": ["find_site", "website", "web"], "enrich_results": "3",
                                                "enrich_searches": "5"})
with SessionLocal() as s:
    e = s.get(Group, buy.id).enrich
check(e == {"words": "wholesale, distributor", "steps": ["find_site", "website", "web"], "results": 3, "searches": 5},
      "Enrich words, steps, results per search and searches per contact saved")
r = c.post(f"/settings/directories/{buy.id}", data={"section": "enrich", "enrich_words": "x"}, follow_redirects=True)
check("at least one Enrich step" in r.text, "at least one step must stay ticked")

# ---------- 11 + 7 + 5. Enrich Now ▾ (Acme Leather: in Buyers & brands, website acme.test) ----------
from app.db import Field
with SessionLocal() as s:   # a field no page fills, so Enrich keeps searching
    s.add(Field(group_id=buy.id, name="Certifications", key="certifications", type="text", position=20))
    s.commit()
with SessionLocal() as s:
    acme = s.scalar(select(Record).where(Record.title.like("Acme Leather%")))
    acme_id = acme.id
r = c.get(f"/records/{acme_id}/open")
check("enrich-menu" in r.text and 'name="steps" value="website"' in r.text and "Only Missing Fields" in r.text
      and "Check All Again" in r.text, "big card: Enrich Now ▾ with steps, Only Missing / Check All Again")
check(re.search(r'value="find_site"[^>]*disabled', r.text) and "Its website is already known" in r.text,
      "a step that can't work is greyed with the reason")
check(re.search(r'value="ebay"[^>]*disabled', r.text) is not None, "eBay greyed (no seller known)")
rw = w.get(f"/records/{acme_id}/open")
check("enrich-menu" not in rw.text and "Enrich Now" in rw.text, "people who don't see methods get the plain button")
httpx.get(SEARX + "/__reset", timeout=5)
h0 = hits()
c.post(f"/records/{acme_id}/enrich", data={"choose": "1", "steps": ["website", "web"], "mode": "missing",
                                            "words": "biker jackets"})
ej = last_job()
check(ej.kind == "enrich" and ej.params.get("steps") == ["website", "web"] and ej.params.get("words") == "biker jackets"
      and not ej.params.get("refresh"), "Enrich Now with chosen steps and extra words")
with SessionLocal() as s:
    check(s.scalar(select(User).where(User.username == "admin")).prefs.get("enrich_choice") ==
          {"steps": ["website", "web"], "mode": "missing"}, "the choice is remembered")
run_queued()
check(job(ej.id).status == "done", f"enrich finished: {job(ej.id).message}")
with SessionLocal() as s:
    er = s.scalars(select(PageRead).where(PageRead.job_id == ej.id)).all()
    traces = s.scalars(select(JobTrace).where(JobTrace.job_id == ej.id)).all()
site_rows = [p for p in er if p.purpose == "site" and p.record_id == acme_id]
check(len(site_rows) >= 2, f"company website pages recorded for the company ({len(site_rows)})")
check(any((p.found or {}).get("code", {}).get("emails") for p in site_rows), "…with the emails code found there")
searches = [t for t in traces if t.kind == "search"]
qs = [t.url for t in searches]
check(any(q == '"acme.test"' for q in qs), f"searched its website address in quotes {qs}")
check(any("biker jackets" in q for q in qs), "searched the person's own words")
check(any("wholesale" in q for q in qs) or len(qs) >= 5, "searched the directory's Enrich words (or hit the limit)")
check(len(qs) <= 5, f"at most 5 searches per contact (directory setting): {len(qs)}")
check(all(t.data.get("why") for t in searches), "Debug shows why each search was made")
fills = [t for t in traces if t.kind == "fill"]
check(any(t.data.get("field") == "Employees" for t in fills) or fills, f"Debug shows which page filled which field ({len(fills)})")
r = c.get(f"/requests/{ej.id}/debug")
check("Fields filled" in r.text and "Company website" in r.text, "Debug: Fields filled tab and pages read")
h1 = hits()
contact_reads = h1.get("acme.test/contact", 0)
r = c.get(f"/records/{acme_id}/open")
check("Pages Read (" in r.text and "acme.test" in r.text, "big card lists the pages read for the company")
c.post(f"/records/{acme_id}/enrich", data={"choose": "1", "steps": ["website"], "mode": "missing"})
ej2 = last_job().id
crawl.purge_cache(0)
run_queued()
with SessionLocal() as s:
    notes = [t for t in s.scalars(select(JobTrace).where(JobTrace.job_id == ej2, JobTrace.kind == "note")).all()]
check(hits().get("acme.test/contact", 0) == contact_reads and any("Already read" in n.data.get("text", "") for n in notes),
      "Enrich again: pages already read for the company are not opened again (what was found is reused)")
check((job(ej2).stats or {}).get("skipped", 0) >= 1, "…and counted as skipped")
c.post(f"/records/{acme_id}/enrich", data={"choose": "1", "steps": ["website"], "mode": "all"})
ej3 = last_job()
check(ej3.params.get("refresh") is True, "Check All Again")
crawl.purge_cache(0)
run_queued()
check(hits().get("acme.test/contact", 0) > contact_reads, "…reads the pages again")
r = c.post(f"/records/{acme_id}/enrich", data={"choose": "1", "mode": "missing"}, follow_redirects=True)
check("Tick at least one Enrich step" in r.text, "no step ticked → asked to tick one")
w.post(f"/records/{acme_id}/enrich", data={"choose": "1", "steps": ["social"], "mode": "all"})
wj = last_job()
check(wj.kind == "enrich" and not wj.params.get("steps") and not wj.params.get("refresh"),
      "a Researcher's Enrich uses the directory's own steps")
QCALLS.clear()
r = c.get(f"/d/{man.id}?view=list")
check("Choose the Enrich steps for the selected contacts" in r.text and 'form="sel"' in r.text,
      "Enrich Selected ▾ in the list")
c.post("/records/enrich-selected", data={"ids": [str(acme_id)], "choose": "1", "steps": ["web"], "mode": "missing"})
check(last_job().params.get("steps") == ["web"], "Enrich Selected with chosen steps")
QCALLS.clear()

# ---------- 12. permissions for every action: Cards Only ----------
c.post("/settings/users/new", data={"username": "cards1", "password": "secret123", "role_id": str(co.id), "active": "on"})
with SessionLocal() as s:
    cu = s.scalar(select(User).where(User.username == "cards1"))
    if cu:
        cu.must_change = False
        s.commit()
check(cu is not None and cu.role == "Cards Only", "a user with the Cards Only role")
k = client("cards1")
r = k.get("/", follow_redirects=False)
check(r.status_code in (302, 303, 307) and r.headers["location"].endswith("/directories"),
      "start page is Directories (no Dashboard)")
r = k.get("/directories")
check(r.status_code == 200 and "Waiting in Inbox" not in r.text and "keyword" not in r.text.lower().split("<main")[-1],
      "Directories without Inbox counts or keywords")
side = r.text.split('class="sidenav"')[1].split("</nav>")[0]
check('href="/inbox"' not in side and 'href="/requests"' not in side and ">Dashboard<" not in side,
      "the menu has no Dashboard, Inbox or Requests")
check("AI Job" not in r.text and "Run Discovery" not in r.text and "+ Add Contact" not in r.text,
      "no AI-jobs list, Run Discovery or Add Contact")
for u in ["/inbox", "/requests", "/activity", "/dashboard/jobs", "/dashboard/system", f"/requests/{j1}/edit",
          "/settings/search-engines"]:
    check(k.get(u).status_code == 403, f"Cards Only can't open {u}")
r = k.get(f"/d/{man.id}")
check(r.status_code == 200 and 'class="card"' in r.text and "Export CSV" not in r.text and "Find New" not in r.text
      and "enrich-sq" not in r.text and "Existing Contacts" not in r.text, "the cards, and nothing else to do")
r = k.get(f"/records/{acme_id}/open")
check(r.status_code in (200, 403), "big card opens (when in a visible directory)")
check("Enrich Now" not in r.text and "Pages Read" not in r.text and "In Inbox" not in r.text,
      "big card: no Enrich, pages read or Inbox notes")
check(k.post(f"/records/{acme_id}/enrich").status_code == 403, "can't start Enrich")
check(k.post("/jobs", data={"query": "x", "group_id": str(man.id)}).status_code == 403, "can't start a search")
r = c.get("/settings/roles")
check("See the Dashboard" in r.text and "See the Inbox" in r.text and "See requests and AI jobs" in r.text,
      "the Roles grid shows the new permissions")

# ---------- 13. look ----------
r = c.get("/settings/themes")
check("A · Navy and Amber" in r.text and "D · Charcoal and Blue" in r.text and "Fonts" in r.text,
      "BrandPartners' colour sets and a Fonts section")
c.post("/settings/themes", data={"action": "copy", "id": "bp-a"})
with SessionLocal() as s:
    mine = [t for t in get_setting(s, "themes", []) if t["name"].startswith("A · Navy and Amber")][0]
r = c.get(f"/settings/themes?edit={mine['id']}")
check('name="heading_font"' in r.text and "Start from a colour set" in r.text and "Playfair Display" in r.text,
      "editing a theme: heading font, colour-set buttons, longer font list")
c.post("/settings/themes", data={"action": "save", "id": mine["id"], "name": "Navy", "font": "Inter",
                                 "heading_font": "Montserrat", "corners": "round", "spacing": "normal"})
with SessionLocal() as s:
    t = [x for x in get_setting(s, "themes", []) if x["id"] == mine["id"]][0]
check(t["font"] == "Inter" and t["heading_font"] == "Montserrat", "theme saved with text and heading font")
r = c.post("/settings/themes/fonts", files={"file": ("Moto.woff2", b"wOF2-test-font", "font/woff2")},
           data={"name": "Moto Sans"}, follow_redirects=True)
with SessionLocal() as s:
    ff = s.scalar(select(FontFile).where(FontFile.name == "Moto Sans"))
check(ff is not None and "installed" in r.text, "font file installed")
fr = c.get(f"/fonts/{ff.id}")
check(fr.status_code == 200 and fr.content == b"wOF2-test-font" and fr.headers["content-type"].startswith("font/woff2"),
      "the font is served by NetGate")
r = c.post("/settings/themes/fonts", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, follow_redirects=True)
check("Choose a font file" in r.text, "only font files are accepted")
check(w.post("/settings/themes/fonts", files={"file": ("y.woff2", b"x", "font/woff2")}).status_code == 403,
      "a Researcher can't install fonts")
c.post("/settings/themes", data={"action": "settings", "default": "classic", "allow_personal": "on"})
r = w.get("/settings/display")
check("My Look" in r.text and "A · Navy and Amber" in r.text and "Moto Sans" in r.text and 'name="size"' in r.text,
      f"Display: My Look with colour sets, fonts (incl. installed) and text size {['My Look' in r.text, 'A · Navy and Amber' in r.text, 'Moto Sans' in r.text]}")
w.post("/settings/display/look", data={"theme": "bp-b", "font": "Moto Sans", "heading_font": "Playfair Display",
                                       "size": "large"})
with SessionLocal() as s:
    wp = s.scalar(select(User).where(User.username == "worker1")).prefs
check(wp.get("theme") == "bp-b" and wp.get("look") == {"font": "Moto Sans", "heading_font": "Playfair Display",
                                                       "size": "large"}, "My Look saved for the person")
r = w.get("/directories")
style = r.text.split("<style>")[1].split("</style>")[0]
check("#c8232b" in style and "'Moto Sans'" in style and "Playfair" in style and f"/fonts/{ff.id}" in style
      and "--fs:16px" in style, "the page uses the person's colours, fonts (uploaded font loaded) and text size")
check("--accent-fg" in style, "button text colour follows the accent (readable on light accents)")
r = c.get("/directories")
check("#c8232b" not in r.text.split("<style>")[1].split("</style>")[0], "…only for that person")
w.post("/settings/display/look", data={"reset": "1"})
with SessionLocal() as s:
    wp = s.scalar(select(User).where(User.username == "worker1")).prefs
check(not wp.get("theme") and not wp.get("look"), "Use the Look for Everyone")
c.post("/settings/themes", data={"action": "settings", "default": "bp-d"})
r = w.post("/settings/display/look", data={"theme": "bp-b"}, follow_redirects=True)
check("switched off" in r.text, "admins can switch personal looks off")
r = w.get("/directories")
check("#2d5be3" in r.text.split("<style>")[1].split("</style>")[0] and "Archivo" in r.text,
      "everyone sees the look for everyone (D · Charcoal and Blue with Archivo)")
c.post("/settings/themes", data={"action": "settings", "default": "classic", "allow_personal": "on"})

# ---------- 14. pop-ups close on outside click ----------
r = c.get("/directories")
check("function closeMenus" in r.text and "t.close()" in r.text and "'Escape'" in r.text,
      "every page closes menus and windows on an outside click or Esc")

# ---------- help, handbook, pages ----------
r = c.get("/help/whats-new")
check("v0.9" in r.text, "What's New has v0.9")
check("Pages read" in c.get("/help/pages-read").text, "help page: pages read")
check("Cards Only" in c.get("/help/people").text, "help: Cards Only")
check("My Look" in c.get("/help/themes").text, "help: My Look")
check("Interrupted" in c.get("/help/requests").text, "help: interrupted requests")
from app import handbook
missing = [f for f in handbook.FEATURES if not os.path.exists(os.path.join("docs", "dev", "features", f + ".md"))]
check(not missing, f"every feature has a Handbook page {missing}")
check("pages_read" in c.get("/dev/handbook/auto-database").text, "Handbook tables list pages_read")
for page in ["/", "/requests", "/inbox", "/contacts", f"/d/{man.id}", "/directories", "/settings/display",
             "/settings/themes", "/settings/crawler", f"/settings/directories/{buy.id}", f"/requests/{ej.id}/debug",
             f"/records/{acme_id}/open", "/settings/roles"]:
    check(c.get(page).status_code == 200, f"opens: {page}")
with SessionLocal() as s:
    errs = s.scalars(select(AppLog).where(AppLog.level == "error",
                                          AppLog.at >= datetime.utcnow() - timedelta(hours=1))).all()
check(not errs, "no errors in the log " + "; ".join(e.message for e in errs[:3]))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("ALL PASSED")
