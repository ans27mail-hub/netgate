"""End-to-end test of NetGate v1.0 on a database made by v0.9 (run tests/test_v09.py first; users admin / worker1 /
viewer1 / dev1 / surfer1, password secret123).
Checks: the upgrade, Dashboard layout and clickable directory cards, the Keyword Library (add, translate, edit,
Search Builder, run in a language, add as keywords, CSV), Browser search with a fake search engine (results, a
CAPTCHA solved by a person in the pop-up, Give Up pauses the engine, Use Again), moving between directories
(preview, Enrich now, Same as, Add This Field), the Company page (found dates, Verify same/changed/not found/gone,
Accept/Keep, profile and products, categories, night verify), the Testing Guide (checklist rules, runs, screenshot,
report, health check, hidden Test Directory, Empty) and permissions.
Real: Postgres, local web pages (tests/fakeweb.py), headless browser (renderer/server.py), fake SearXNG
(tests/fake_searx.py), fake search engine for Browser search (tests/fake_engine.py).
Simulated inside the test: the AI and the queue."""
import os

os.environ.setdefault("BROWSER_ENGINE_URLS", '{"bing": "http://127.0.0.1:3996/bing?q={q}&first={first}", '
                                             '"duckduckgo": "http://127.0.0.1:3996/ddg?q={q}&s={first0}"}')
import re
import sys
import threading
import time
from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app import ai, browser, crawl, jobs, testguide
from app.db import (AppLog, CaptchaWait, Field, Group, InboxItem, Job, Keyword, KwCategory, KwTerm, KwTranslation, Membership,
                    Product, Record, Role, SearchLog, SessionLocal, Setting, TestRun, TestShot, User, get_setting,
                    set_setting)

fails = []
ENGINE = "http://127.0.0.1:3996"
SEARX = os.environ.get("SEARXNG_URL", "http://127.0.0.1:3997")
RENDER = os.environ.get("RENDER_URL", "http://127.0.0.1:3999")


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


LINE = re.compile(r"([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2}) — ([A-Za-z]+), ([A-Za-z]+)")
TRANSLATIONS = {"de": {"racing gloves": "Rennhandschuhe", "leather jackets": "Lederjacken", "germany": "Deutschland"}}


def fake_ask(job_type, prompt, timeout=300):
    if prompt.startswith("Translate these search keywords"):
        lang = "de" if "German" in prompt else ""
        words = re.findall(r"^- (.+)$", prompt, re.M)
        return {"translations": {w: TRANSLATIONS.get(lang, {}).get(w.lower()) for w in words
                                 if TRANSLATIONS.get(lang, {}).get(w.lower())}}
    if "Write a short profile" in prompt:
        return {"type": "manufacturer", "summary": "Acme Leather makes leather motorbike gloves and jackets.",
                "categories": ["Motorbike Gloves", "Spaceships"], "main_products": ["Racing gloves", "Jackets"],
                "materials": ["Cowhide"], "markets": ["Europe"], "certifications": [], "founded": "1990",
                "products": [{"name": "Racing Glove RG-1", "category": "Motorbike Gloves", "moq": "300 pairs"},
                             {"name": "Touring Jacket TJ", "category": "Motorbike Leather Jackets"},
                             {"name": "Racing Glove RG-1", "category": "Motorbike Gloves"}]}
    if "Find its" in prompt:
        return {"value": None}
    if "List every" in prompt:
        body = prompt.split("Page text:", 1)[1]
        return {"entries": [{"name": n, "city": c, "country": k, "website": None, "description": f"{n} makes gloves.",
                             "fields": {}} for n, c, k in LINE.findall(body)]}
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


def set_page(host, path, body=""):
    httpx.post(f"http://127.0.0.1/__set?host={host}&path={path}", content=body.encode(), timeout=5)


app = __import__("app.main", fromlist=["app"]).app


def client(name, password="secret123"):
    cl = TestClient(app)
    cl.__enter__()
    cl.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    return cl


c = client("admin")
w = client("worker1")    # Researcher
v = client("viewer1")    # Viewer
d = client("dev1")       # Developer
crawl.purge_cache(0)
httpx.get(f"{ENGINE}/__captcha?on=0", timeout=5)
httpx.get(f"{ENGINE}/__reset", timeout=5)
for sid in ("eng-bing", "eng-duckduckgo"):
    try:
        httpx.post(f"{RENDER}/session/close?sid={sid}", timeout=10)
    except httpx.HTTPError:
        pass

# ---------- upgrade ----------
check(c.get("/health").json().get("version") == "v1.0", "version v1.0")
with SessionLocal() as s:
    check(s.get(Setting, "v10_upgraded") is not None, "v1.0 upgrade ran")
    roles = {r.name: r for r in s.scalars(select(Role)).all()}
    check(all("manage_keywords" in r.perm_set for r in roles.values() if "manage_dirs" in r.perm_set),
          "roles that manage directories may manage the keyword library")
    check("testing" in roles["Developer"].perm_set if "Developer" in roles else True, "Developer role has Testing Guide")
    check("testing" not in roles["Researcher"].perm_set and "testing" not in roles["Viewer"].perm_set,
          "Researcher and Viewer don't have Testing Guide")
    cats = {cc.name: cc for cc in s.scalars(select(KwCategory)).all()}
    check("Products" in cats and "Countries and cities" in cats, "keyword library starts with example categories")
    fromdir = cats.get("From directories")
    kws = s.scalars(select(Keyword)).all()
    check(fromdir is not None and all(k.term_ids for k in kws), "existing directory keywords are in the library and linked")
    cols = {r[0] for r in s.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='records'"))}
    check({"meta", "profile"} <= cols, "records have meta and profile")
    tables = {r[0] for r in s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
    check({"products", "test_runs", "test_shots", "captcha_waits", "kw_terms", "kw_categories", "kw_translations"} <= tables,
          "new tables made")
    groups = {g.name: g for g in s.scalars(select(Group)).all()}
    man, mat, buy = groups["Manufacturers"], groups["Materials"], groups["Buyers & brands"]
    admin = s.scalar(select(User).where(User.username == "admin"))
    acme = s.scalar(select(Record).where(Record.title.ilike("acme%")))
    acme_id = acme.id

# ---------- 15. Dashboard layout, 18. clickable directory cards ----------
r = c.get("/")
check('class="panel dash-attn' in r.text or "dash-attn" in r.text, "Needs Attention has its own box class")
check("dash-jobs" in r.text, "Running Jobs has its own box class")
css = c.get("/static/app.css").text
check("repeat(auto-fit, minmax(170px, 1fr))" in css and ".dash-attn, .dash-jobs" in css,
      "tiles fill the width; Needs Attention and Running Jobs are equal width")
r = c.get("/directories?view=grid")
check(f'data-href="/d/{man.id}"' in r.text and "dircard clickable" in r.text, "directory cards open on a click anywhere")
r = c.get("/directories?view=list")
check('class="rowlink"' in r.text, "directory list rows open on a click anywhere")
check("[data-href]" in r.text or "data-href" in c.get("/").text, "every page has the click-anywhere handler")

# ---------- 17. Keyword Library ----------
r = c.get("/keywords")
check(r.status_code == 200 and "Products" in r.text, "Keywords page opens")
prod_id, place_id = cats["Products"].id, cats["Countries and cities"].id
r = c.post("/keywords/terms/add", data={"category_id": prod_id, "text": "racing gloves\nRacing Gloves\nleather jackets"},
           follow_redirects=False)
c.post("/keywords/terms/add", data={"category_id": place_id, "text": "Germany"}, follow_redirects=False)
with SessionLocal() as s:
    def term(t):
        return s.scalar(select(KwTerm).where(KwTerm.norm == t))
    rg, lj, de_ = term("racing gloves"), term("leather jackets"), term("germany")
    n_rg = s.scalar(select(func.count(KwTerm.id)).where(KwTerm.norm == "racing gloves"))
check(rg and lj and de_ and n_rg == 1, "words added, the same word is not added twice")
r = c.post("/keywords/terms/bulk", data={"ids": [rg.id, lj.id, de_.id], "action": "translate", "lang": "de"},
           follow_redirects=False)
with SessionLocal() as s:
    tr = {t.term_id: t for t in s.scalars(select(KwTranslation).where(KwTranslation.lang == "de")).all()}
check(tr.get(rg.id) and tr[rg.id].text == "Rennhandschuhe" and tr[rg.id].source == "ai" and not tr[rg.id].checked,
      "Translate (German): the AI translates once, saved as unchecked AI translation")
check(tr.get(de_.id) and tr[de_.id].text == "Deutschland", "…places too")
r = c.post(f"/keywords/terms/{rg.id}", data={"text": "racing gloves", "category_id": prod_id, "active": "on",
                                             "tr_de": "Motorrad Rennhandschuhe", "ok_de": "on", "notes": ""},
           follow_redirects=False)
with SessionLocal() as s:
    t = s.scalar(select(KwTranslation).where(KwTranslation.term_id == rg.id, KwTranslation.lang == "de"))
check(t.text == "Motorrad Rennhandschuhe" and t.source == "person" and t.checked, "a person edits and checks a translation")
r = c.get(f"/keywords/build?group={man.id}&lang=&lang=de&c_{prod_id}={rg.id}&c_{place_id}={de_.id}")
check(r.status_code == 200 and "Motorrad Rennhandschuhe Deutschland" in r.text and "racing gloves Germany" in r.text,
      "Search Builder shows each combination in English and German")
httpx.get(f"{SEARX}/__reset", timeout=5)
QCALLS.clear()
r = c.post("/keywords/build", data={"group_id": man.id, "action": "run", "combo": [f"de|{rg.id},{de_.id}"]},
           follow_redirects=False)
jb = last_job()
check(jb.params.get("lang") == "de" and jb.params.get("terms") == [rg.id, de_.id] and jb.query == "racing gloves Germany",
      "Run Now starts a request with the words and the language")
run_queued()
calls = httpx.get(f"{SEARX}/__calls", timeout=5).json()
check(any(cl["q"].startswith("Motorrad Rennhandschuhe Deutschland") for cl in calls), "…it searches with the German words")
check("German" in job(jb.id).message, "…and the request says which language it searched in")
with SessionLocal() as s:
    check((s.get(KwTerm, rg.id).uses or 0) >= 1, "the library counts how often a word was used")
r = c.post("/keywords/build", data={"group_id": man.id, "action": "add", "combo": [f"de|{rg.id},{de_.id}"]},
           follow_redirects=False)
with SessionLocal() as s:
    k = s.scalar(select(Keyword).where(Keyword.group_id == man.id, Keyword.text == "racing gloves Germany"))
check(k is not None and k.lang == "de" and k.term_ids == [rg.id, de_.id], "Add to Directory Keywords keeps words and language")
r = c.get(f"/keywords/build?group={man.id}&lang=de&c_{prod_id}={rg.id}&c_{place_id}={de_.id}")
check("already a keyword here" in r.text and "searched in the last 14 days" in r.text, "Search Builder warns about repeats")
csv_text = c.get("/keywords/export.csv").text
check("Motorrad Rennhandschuhe" in csv_text, "CSV export has translations")
with SessionLocal() as s:
    before = s.scalar(select(func.count(KwTerm.id)))
c.post("/keywords/import", files={"file": ("k.csv", csv_text.encode(), "text/csv")}, follow_redirects=False)
with SessionLocal() as s:
    check(s.scalar(select(func.count(KwTerm.id))) == before, "importing the same CSV adds no duplicates")
check(w.get("/keywords").status_code == 200, "a Researcher can open the library (to pick words)")
check(w.post("/keywords/terms/add", data={"category_id": prod_id, "text": "x"}, follow_redirects=False).status_code == 403,
      "…but can't change it")
check(v.get("/keywords").status_code == 403, "a Viewer can't open the library")
r = c.get(f"/settings/directories/{man.id}")
check('name="langs"' in r.text and "Add From the Keyword Library" in r.text, "Directory Settings: languages and library")
r = c.get(f"/requests/{jb.id}/edit")
check("Pick From the Keyword Library" in r.text, "Edit and Run Again: Pick From the Keyword Library")

# ---------- 16. Testing Guide: checklist rules ----------
from app import handbook
from app.web.common import VERSION
lists = testguide.checklists()
covered = {cl["feature"] for cl in lists} | {cl["slug"] for cl in lists}
missing = [f for f in handbook.FEATURES if f not in covered]
check(not missing, f"every Handbook feature has a Testing Guide checklist {missing}")
check(any(st["since"] == VERSION for cl in lists for st in cl["steps"]),
      f"this version ({VERSION}) added checklist steps")
check(all(cl["steps"] and all(st["do"] and st["expect"] for st in cl["steps"]) for cl in lists),
      "every step says what to do and what you should see")
check(d.get("/testing").status_code == 200, "a Developer opens the Testing Guide")
check(w.get("/testing").status_code == 403 and v.get("/testing").status_code == 403, "Researcher and Viewer can't")

# Test Directory
r = c.post("/testing/test-directory/create", follow_redirects=False)
with SessionLocal() as s:
    tg = s.scalar(select(Group).where(Group.is_test))
check(tg is not None and r.headers["location"] == f"/d/{tg.id}", "Make the Test Directory")
check(c.get(f"/d/{tg.id}").status_code == 200 and w.get(f"/d/{tg.id}").status_code == 403,
      "its page needs the Testing Guide permission")
check(tg.name not in c.get("/directories").text and tg.name not in w.get("/").text, "it is hidden from the directory lists")
r = c.get(f"/d/{tg.id}")
check(f'value="{tg.id}"' in r.text, "on its own page it can be chosen for Run Discovery")

# ---------- 4. Browser search ----------
r = c.post("/settings/browser", data={"engines": ["bing"], "pause": "5", "per_hour": "50", "captcha_hours": "6",
                                      "wait_minutes": "1"}, follow_redirects=False)
with SessionLocal() as s:
    cfg = browser.settings(s)
    g = s.get(Group, tg.id)
    g.methods = {"browser": {"want": 20, "max_pages": 1, "max_minutes": 5, "engines": ["bing"]}}
    s.commit()
check(cfg["engines"] == ["bing"] and cfg["wait_minutes"] == 1, "Browser search settings saved")
r = c.get("/settings/search-engines")
check('id="browser"' in r.text and "Browser Search" in r.text, "Settings → Search Engines has Browser Search")
r = c.get(f"/settings/directories/{tg.id}")
check("Browser" in r.text, "Directory Settings shows the Browser Search method")


def new_request(q, gid, uid):
    with SessionLocal() as s:
        j = Job(query=q, group_id=gid, kind="request", user_id=uid, status="queued", stats={},
                params={"methods": ["browser"]})
        s.add(j)
        s.commit()
        return j.id


j1 = new_request("glove makers", tg.id, admin.id)
jobs.run_job(j1)
calls = httpx.get(f"{ENGINE}/__calls", timeout=5).json()
with SessionLocal() as s:
    found = s.scalars(select(InboxItem).where(InboxItem.group_id == tg.id)).all()
    logged = s.scalars(select(SearchLog).where(SearchLog.job_id == j1)).all()
check(any(cl["path"] == "/bing" and cl["q"] == "glove makers" for cl in calls), "Browser search opens the engine's page")
check(len(found) >= 2 and job(j1).status == "done", f"…reads the result links and finds companies ({len(found)})")
check(any(x.asked == ["browser:bing"] for x in logged), "…and writes the search to the search log")

# CAPTCHA solved by a person
httpx.get(f"{ENGINE}/__captcha?on=1", timeout=5)
j2 = new_request("glove makers page two", tg.id, admin.id)
th = threading.Thread(target=jobs.run_job, args=(j2,))
th.start()
wid = None
for _ in range(60):
    time.sleep(1)
    with SessionLocal() as s:
        cw = s.scalar(select(CaptchaWait).where(CaptchaWait.job_id == j2))
        if cw and cw.status == "waiting":
            wid = cw.id
            break
check(wid is not None, "a CAPTCHA makes the search wait for a person")
mine = c.get("/captcha/mine").json()
check(mine.get("popup") == wid and mine.get("engine") == "Bing", "the person who started it gets the pop-up")
check(w.get("/captcha/mine").json().get("popup") is None, "…other people don't")
check("CAPTCHA" in c.get("/").text and f"/captcha/{wid}" in c.get("/").text, "Dashboard Needs Attention: Solve")
r = c.get(f"/captcha/{wid}?frame=1")
check(r.status_code == 200 and 'id="capimg"' in r.text and "<!doctype html>" in r.text, "the pop-up page shows the picture")
shot = c.get(f"/captcha/{wid}/shot")
check(shot.status_code == 200 and shot.content[:4] == b"\x89PNG", "…a live screenshot of NetGate's browser")
check(w.get(f"/captcha/{wid}").status_code == 403, "someone who may not control the request can't open it")
res = c.post(f"/captcha/{wid}/click", data={"x": "500", "y": "400"}).json()
check(res.get("status") == "solved", "a person's click solves it")
th.join(90)
with SessionLocal() as s:
    cw = s.get(CaptchaWait, wid)
check(cw.status == "solved" and cw.solved_by == admin.id, "…recorded as solved by that person")
check(job(j2).status == "done", "…and the search goes on to the end")

# CAPTCHA given up → engine paused
httpx.post(f"{RENDER}/session/close?sid=eng-bing", timeout=10)
j3 = new_request("glove makers three", tg.id, admin.id)
th = threading.Thread(target=jobs.run_job, args=(j3,))
th.start()
wid3 = None
for _ in range(60):
    time.sleep(1)
    with SessionLocal() as s:
        cw = s.scalar(select(CaptchaWait).where(CaptchaWait.job_id == j3))
        if cw and cw.status == "waiting":
            wid3 = cw.id
            break
res = c.post(f"/captcha/{wid3}/giveup").json() if wid3 else {}
th.join(90)
httpx.get(f"{ENGINE}/__captcha?on=0", timeout=5)
with SessionLocal() as s:
    cfg = browser.settings(s)
check(res.get("status") == "gave_up" and browser.paused_until(cfg, "bing") is not None, "Give Up pauses the engine")
check("paused" in (job(j3).message or ""), "…and the request says so")
r = c.get("/settings/search-engines")
check("Use Again Now" in r.text, "Settings shows the paused engine with Use Again Now")
j4 = new_request("glove makers four", tg.id, admin.id)
jobs.run_job(j4)
check("paused" in (job(j4).message or "") or "no search engine" in (job(j4).message or ""),
      "while paused, Browser search doesn't use that engine")
c.post("/settings/browser", data={"resume": "bing"}, follow_redirects=False)
with SessionLocal() as s:
    check(browser.paused_until(browser.settings(s), "bing") is None, "Use Again Now ends the pause")

# ---------- 8. moving between directories ----------
from app import contacts as CT
with SessionLocal() as s:
    mids = [m.record_id for m in s.scalars(select(Membership).where(Membership.group_id == man.id)).all()]
    mat_keys = {f.key for f in s.get(Group, mat.id).fields}
    man_keys = {f.key for f in s.get(Group, man.id).fields}
    # the Manufacturers contact with most details Materials has no field for
    other = max(mids, key=lambda i: (len([k for k, val in (s.get(Record, i).data or {}).items()
                                          if k not in mat_keys and val not in (None, "", [])]), -i))
    # a brand-new company (Materials fields only) for the “missing fields” preview
    fresh, created, _ = CT.upsert(s, name="Fresh Trims Co", values={"city": "Lahore", "website": "http://fresh.test/"},
                                  sources={"city": "http://fresh.test/", "website": "http://fresh.test/"},
                                  source_url="http://fresh.test/", added_by=admin.id)
    s.add(Membership(record_id=fresh.id, group_id=mat.id))
    s.commit()
    fresh_id = fresh.id
    fmeta = dict(fresh.meta or {})
check(created and fmeta.get("city", {}).get("at") and fmeta.get("website", {}).get("at"),
      "a new company's values get a found date")
r = c.get(f"/records/{other}/move-preview?group_id={mat.id}&from_id={man.id}")
check("Kept but hidden" in r.text and "Other Details" in r.text, "move preview: details kept but hidden")
r = c.get(f"/records/{fresh_id}/move-preview?group_id={man.id}&from_id={mat.id}")
check("Missing in Manufacturers" in r.text and 'name="enrich_now"' in r.text,
      "move preview: fields missing there, with Enrich the missing fields now")
r = c.get(f"/records/move-preview?group_id={mat.id}&ids={mids[0]}&ids={mids[-1]}")
check(r.status_code == 200 and r.text.strip() != "", "move preview for several contacts")
QCALLS.clear()
r = c.post(f"/records/{other}/directories", data={"group_id": mat.id, "from_id": man.id, "action": "move",
                                                  "enrich_now": "on"}, follow_redirects=False)
with SessionLocal() as s:
    gids = {m.group_id for m in s.scalars(select(Membership).where(Membership.record_id == other)).all()}
check(mat.id in gids and man.id not in gids, "Move Here moves the contact")
check(any(a[2] and job(a[2][0]) and job(a[2][0]).kind == "enrich" for a in QCALLS), "…and “Enrich the missing fields now” starts Enrich")
QCALLS.clear()
r = c.get(f"/records/{other}/open?from={mat.id}")
check("Other Details" in r.text and "Add This Field to" in r.text, "big card: Other Details with Add This Field")
with SessionLocal() as s:
    rec = s.get(Record, other)
    hidden = [k for k, val in (rec.data or {}).items() if k not in mat_keys and val not in (None, "", [])]
if hidden:
    c.post(f"/settings/directories/{mat.id}/adopt-field", data={"key": hidden[0], "back": str(other)},
           follow_redirects=False)
    with SessionLocal() as s:
        check(hidden[0] in {f.key for f in s.get(Group, mat.id).fields}, "Add This Field adds it to the directory")
with SessionLocal() as s:
    g = s.get(Group, buy.id)
    bf = next(f for f in g.fields if f.key == "city")
    taken = {f.key for f in g.fields}
    free = next(k for k in ("contact_email", "products", "phone", "employees") if k not in taken)
r = c.post(f"/settings/directories/{buy.id}/fields/{bf.id}/same-as", data={"other": "country"}, follow_redirects=False)
with SessionLocal() as s:
    check(s.get(Group, buy.id).links in (None, {}) and s.get(Field, bf.id).key == "city",
          "Same as refuses a field the directory already has")
r = c.post(f"/settings/directories/{buy.id}/fields/{bf.id}/same-as", data={"other": free}, follow_redirects=False)
with SessionLocal() as s:
    g = s.get(Group, buy.id)
    check(s.get(Field, bf.id).key == free and (g.links or {}).get(str(bf.id)) == {"own": "city", "same_as": free},
          "Same as links the field to another directory's field")
r = c.post(f"/settings/directories/{buy.id}/fields/{bf.id}/same-as", data={"other": ""}, follow_redirects=False)
with SessionLocal() as s:
    check(s.get(Field, bf.id).key == "city" and not (s.get(Group, buy.id).links or {}), "…and choosing nothing goes back")
r = c.get(f"/settings/directories/{buy.id}")
check("Same as" in r.text, "Directory Settings → Fields has Same as")

# ---------- 1. Company page, Verify, profile, products ----------
r = c.post(f"/records/{fresh_id}/edit", data={"title": "Fresh Trims Co", "f_city": "Lahore City"},
           follow_redirects=False)
with SessionLocal() as s:
    rec = s.get(Record, fresh_id)
    check((rec.meta or {}).get("city", {}).get("at") and rec.sources["city"] == "edited by admin",
          "editing a value stamps the date it was found")
r = c.get(f"/companies/{acme_id}")
check(r.status_code == 200 and "Read from a page" in r.text and "Verify All Details" in r.text, "Company page opens")
check("Company Page" in c.get(f"/records/{acme_id}/open").text, "the big card links to the Company page")
set_page("acme.test", "/contact", '<html><body><h1>Contact Acme Leather</h1><p>Write to export@acme.test.</p>'
         '<a href="https://wa.me/923001112223">WhatsApp</a><p>Acme Leather contact page, Sialkot Pakistan.</p></body></html>')
set_page("acme.test", "/about-us", "<html><body><h1>About Acme Leather</h1><p>We make gloves in Sialkot for brands.</p></body></html>")
set_page("acme.test", "/impressum", "<html><body>x</body></html>")
QCALLS.clear()
c.post(f"/companies/{acme_id}/verify", follow_redirects=False)
vj = last_job()
check(vj.kind == "verify" and vj.record_id == acme_id, "Verify All Details starts a Verify request")
run_queued()
with SessionLocal() as s:
    meta = s.get(Record, acme_id).meta or {}
st = {k: (m.get("verify") or {}).get("status") for k, m in meta.items() if isinstance(m, dict)}
check(st.get("city") == "same" and st.get("website") == "same", "Verify: values still on the page are the same")
check(st.get("country") == "same" and st.get("address") == "same", "Verify: values the page writes differently (PK → Pakistan) count as the same")
check(st.get("contact_email") == "changed" and meta["contact_email"]["verify"].get("new") == "export@acme.test",
      "Verify: a changed email is found by code, with the new value")
check(st.get("employees") == "not_found", "Verify: a value gone from the page is Not found (AI asked, said nothing)")
check(st.get("phone") == "gone", "Verify: a page that can't be read is marked")
check(meta.get("_verified") and meta["city"].get("checked"), "…dates of the check are kept")
with SessionLocal() as s:
    check(s.get(Record, acme_id).data.get("contact_email") == "sales@acme.test", "nothing changes before a person decides")
    from app.db import PageRead
    check(s.scalar(select(func.count(PageRead.id)).where(PageRead.job_id == vj.id, PageRead.purpose == "verify")) >= 3,
          "Verify pages are in the list of pages read")
check("Changed?" in c.get(f"/records/{acme_id}/open").text, "the big card flags a changed detail")
r = c.get(f"/companies/{acme_id}")
check("Accept New Value" in r.text and "export@acme.test" in r.text and "Keep Old" in r.text, "Company page: Accept / Keep")
check(v.post(f"/companies/{acme_id}/accept", data={"key": "contact_email"}, follow_redirects=False).status_code == 403,
      "a Viewer can't accept a new value")
c.post(f"/companies/{acme_id}/accept", data={"key": "contact_email"}, follow_redirects=False)
c.post(f"/companies/{acme_id}/keep", data={"key": "employees"}, follow_redirects=False)
with SessionLocal() as s:
    rec = s.get(Record, acme_id)
check(rec.data["contact_email"] == "export@acme.test" and rec.sources["contact_email"] == "http://acme.test/contact"
      and rec.meta["contact_email"]["verify"]["status"] == "accepted", "Accept New Value saves it")
check(rec.data.get("employees") == "51–200" and rec.meta["employees"]["verify"]["status"] == "kept", "Keep Old keeps it")
check(any("accepted by admin" in h["text"] for h in rec.history), "…and History says who")
set_page("acme.test", "/contact")
set_page("acme.test", "/about-us")
set_page("acme.test", "/impressum")
check(v.get(f"/companies/{acme_id}").status_code in (200, 403), "a Viewer may only look")
check(v.post(f"/companies/{acme_id}/verify", follow_redirects=False).status_code == 403, "…and can't start Verify")

# profile and products
home = httpx.get("http://acme.test/", timeout=5).text
set_page("acme.test", "/", home.replace('<a href="/contact">', '<a href="/products">Products</a><a href="/contact">'))
crawl.purge_cache(0)
QCALLS.clear()
c.post(f"/companies/{acme_id}/profile", follow_redirects=False)
pj = last_job()
run_queued()
with SessionLocal() as s:
    rec = s.get(Record, acme_id)
    prods = s.scalars(select(Product).where(Product.record_id == acme_id).order_by(Product.id)).all()
p = rec.profile or {}
check(job(pj.id).status == "done" and p.get("type") == "manufacturer", "Make Profile: the AI's short profile is saved")
check(p.get("categories") == ["Motorbike Gloves"], "…only categories from the list are kept")
check(any("/products" in u for u in p.get("pages") or []), "…it read the products page")
check(len(prods) == 2 and prods[0].image_url == "http://acme.test/img/racing-glove.jpg" and prods[0].moq == "300 pairs",
      "products saved once each, with the picture link from the page")
r = c.post(f"/companies/{acme_id}/product-add", data={"name": "Kids Gloves", "category": "Kids Motorbike Wear"},
           follow_redirects=False)
c.post(f"/companies/{acme_id}/profile", follow_redirects=False)
run_queued()
with SessionLocal() as s:
    prods = s.scalars(select(Product).where(Product.record_id == acme_id)).all()
check(len(prods) == 3 and any(pr.name == "Kids Gloves" and pr.added_by for pr in prods),
      "making the profile again keeps products a person added")
kid = next(pr.id for pr in prods if pr.name == "Kids Gloves")
c.post(f"/companies/{acme_id}/product-delete", data={"pid": kid}, follow_redirects=False)
with SessionLocal() as s:
    check(s.get(Product, kid) is None, "Remove deletes a product")
r = c.get(f"/companies/{acme_id}")
check("Racing Glove RG-1" in r.text and "Cowhide" in r.text, "Company page shows profile and products")
set_page("acme.test", "/")
r = c.post("/settings/product-categories", data={"cats": "Gloves\nJackets\nGloves"}, follow_redirects=False)
with SessionLocal() as s:
    check(get_setting(s, "product_categories") == ["Gloves", "Jackets"], "Product Categories saved (no doubles)")
c.post("/settings/product-categories", data={"reset": "1"}, follow_redirects=False)
check("Motorbike Gloves" in c.get("/settings/product-categories").text, "Back to the Starting List")
check(w.get("/settings/product-categories").status_code == 403, "Product Categories need Manage directories")

# night verify
with SessionLocal() as s:
    saved_groups = {g.id: (g.night_discover, g.night_enrich, g.refresh_days) for g in s.scalars(select(Group)).all()}
    for g in s.scalars(select(Group)).all():
        g.night_discover, g.night_enrich, g.refresh_days = False, False, 0
    rec = s.get(Record, acme_id)
    rec.created_at = datetime.utcnow() - timedelta(days=200)
    rec.meta = {**(rec.meta or {}), "_verified": "2020-01-01T00:00:00"}
    cfg = jobs.night_settings(s)
    set_setting(s, "night", {**cfg, "verify_months": 3, "verify_max": 5, "enrich_inbox": False})
    from app.db import NightRun
    nr = NightRun(night_date=(datetime.utcnow() + timedelta(days=400)).date(), status="running", stats={})
    s.add(nr)
    s.commit()
    nr_id = nr.id
real_in_window = jobs.in_window
jobs.in_window = lambda cfg, now: True
ctx = jobs.Ctx(None, "night")
jobs.run_night(ctx, nr_id)
jobs.in_window = real_in_window
with SessionLocal() as s:
    rec = s.get(Record, acme_id)
    check(ctx.stats.get("verified", 0) >= 1 and rec.meta.get("_verified", "") > "2021", "the night run verifies old contacts")
    for gid, (a, b, cc) in saved_groups.items():
        g = s.get(Group, gid)
        g.night_discover, g.night_enrich, g.refresh_days = a, b, cc
    s.commit()
r = c.get("/settings/night")
check('name="verify_months"' in r.text, "Night Jobs: Verify contacts not checked for … months")

# ---------- 16. Testing Guide: runs ----------
r = c.post("/testing/runs", data={"scope": "new"}, follow_redirects=False)
run_url = r.headers["location"]
rid = int(run_url.rsplit("/", 1)[1])
new_steps = [st for cl in lists for st in cl["steps"] if st["since"] == VERSION]
r = c.get(run_url)
check(r.status_code == 200 and r.text.count('class="tstep ') == len(new_steps), "a “new only” run lists this version's steps")
first, second = new_steps[0]["id"], new_steps[1]["id"]
r = c.post(run_url + "/step", data={"step": first, "ok": "pass", "note": ""})
check(r.status_code == 200 and "is-pass" in r.text and "admin" in r.text, "Passed saves at once and shows who")
png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
r = c.post(run_url + "/step", data={"step": second, "ok": "fail", "note": "the tiles stay on the left"},
           files={"shot": ("s.png", png, "image/png")})
check("is-fail" in r.text and "/testing/shots/" in r.text, "Failed with a note and a screenshot")
r = c.post(run_url + "/step", data={"step": "nonsense:1", "ok": "pass"})
check(r.status_code == 403, "unknown steps are refused")
with SessionLocal() as s:
    sh = s.scalar(select(TestShot).where(TestShot.run_id == rid))
check(sh is not None and c.get(f"/testing/shots/{sh.id}").content == png, "the screenshot is kept")
r = c.post(run_url + "/step", data={"step": first, "ok": "pass"}, files={"shot": ("x.exe", b"MZ", "application/octet-stream")})
with SessionLocal() as s:
    check(s.scalar(select(func.count(TestShot.id)).where(TestShot.run_id == rid)) == 1, "only pictures are accepted")
r = c.get(run_url + "?only=fail")
check(r.text.count('class="tstep ') == 1 and "the tiles stay on the left" in r.text, "Failed shows only failed steps")
check("Note: the tiles stay on the left" in r.text and "failed steps:" in r.text, "the Report lists failed steps with notes")
c.post(run_url + "/finish", follow_redirects=False)
with SessionLocal() as s:
    run = s.get(TestRun, rid)
n = testguide.counts(run)
check(run.finished_at and n["pass"] == 1 and n["fail"] == 1 and n["todo"] == len(new_steps) - 2, "Finish Run keeps the numbers")
check(c.post(run_url + "/step", data={"step": first, "ok": "fail"}).status_code == 403, "a finished run can't change")
r = c.get("/testing")
check(f"/testing/runs/{rid}" in r.text and VERSION in r.text, "runs are listed per version")
check(d.post(run_url + "/delete", follow_redirects=False).status_code == 403, "only its tester or an admin deletes a run")
r = c.post("/testing/runs", data={"scope": "all"}, follow_redirects=False)
check(c.get(r.headers["location"]).text.count('class="tstep ') == sum(len(cl["steps"]) for cl in lists),
      "an “everything” run lists every step")

# Quick Health Check is read-only
with SessionLocal() as s:
    counts_before = [s.scalar(select(func.count(m.id))) for m in (Job, Record, AppLog, InboxItem)]
r = c.get("/testing/health")
with SessionLocal() as s:
    counts_after = [s.scalar(select(func.count(m.id))) for m in (Job, Record, AppLog, InboxItem)]
check(r.status_code == 200 and "Database" in r.text and "Browser (renderer)" in r.text and "Queue" in r.text,
      "Quick Health Check shows each part")
check(counts_before == counts_after, "…and changes nothing")
check(w.get("/testing/health").status_code == 403, "…only with the Testing Guide permission")

# Test Directory stays apart, then Empty
with SessionLocal() as s:
    ids = []
    for nm in ("Testonly Gloves", "Shared Gloves"):
        rec, _, _ = CT.upsert(s, name=nm, values={"city": "Sialkot"}, sources={"city": "test"}, added_by=admin.id)
        s.flush()
        it = CT.to_inbox(s, rec, tg.id, method="web", keyword="test")
        s.flush()
        CT.accept(s, it, s.get(User, admin.id), tg.id)
        ids.append(rec.id)
    s.add(Membership(record_id=ids[1], group_id=buy.id))
    s.commit()
    a_id, b_id, a_title = ids[0], ids[1], "Testonly"
    waiting = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.group_id == tg.id, InboxItem.status == "new"))
check(waiting >= 1, "Browser search results are waiting in the Test Directory's Inbox")
r = c.get("/contacts?q=" + a_title.split()[0])
check(f"/records/{a_id}/" not in r.text, "Test Directory contacts are not in All Contacts")
check(f"/records/{a_id}/" in c.get(f"/d/{tg.id}").text, "…they are on the Test Directory page")
r = c.post("/testing/test-directory/empty", follow_redirects=False)
with SessionLocal() as s:
    check(s.get(Record, a_id) is None, "Empty Test Directory deletes its contacts")
    check(s.get(Record, b_id) is not None and s.scalar(select(Membership).where(Membership.record_id == b_id,
                                                                               Membership.group_id == buy.id)),
          "…but keeps a contact that is also in a real directory")
    check(not s.scalar(select(func.count(InboxItem.id)).where(InboxItem.group_id == tg.id)), "…and its Inbox items")
    check(all(j.deleted_at for j in s.scalars(select(Job).where(Job.group_id == tg.id)).all()), "…and its requests")
    check(s.get(Group, tg.id) is not None, "the Test Directory itself stays, empty")

# ---------- help, handbook, pages ----------
r = c.get("/help/whats-new")
check("v1.0" in r.text, "What's New has v1.0")
for slug, word in [("keywords", "Search Builder"), ("browser-search", "CAPTCHA"), ("company-page", "Verify"),
                   ("testing-guide", "Test Directory"), ("move-contacts", "Same as"), ("night-jobs", "Verify")]:
    check(word in c.get(f"/help/{slug}").text, f"help page {slug} explains {word}")
missing = [f for f in handbook.FEATURES if not os.path.exists(os.path.join("docs", "dev", "features", f + ".md"))]
check(not missing, f"every feature has a Handbook page {missing}")
r = c.get("/dev/handbook/auto-database")
check("products" in r.text and "test_runs" in r.text, "Handbook tables list the new tables")
for page in ["/", "/requests", "/inbox", "/contacts", f"/d/{man.id}", "/directories", "/keywords", "/keywords/build",
             f"/keywords/terms/{rg.id}", "/testing", "/testing/health", f"/companies/{acme_id}",
             "/settings/product-categories", "/settings/search-engines", f"/settings/directories/{man.id}",
             f"/records/{acme_id}/open", "/settings/night", "/settings/roles", f"/captcha/{wid}"]:
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
