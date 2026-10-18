"""End-to-end test of NetGate v0.8 on a database made by v0.7 (run tests/test_v07.py with the v0.7 code first;
users admin / worker1 / viewer1 / dev1 / surfer1, password secret123).
Checks: deleting only empty directories, Fill the row, Edit and Run Again (tries, Go Deeper, Save as Keyword,
nothing-found hint, permissions), Settings → Search Engines (choice sent to SearXNG, working / blocking since,
Test Now, Debug engines, Dashboard warning, log clean-up).
Real: Postgres, local web pages (tests/fakeweb.py), headless browser, a fake SearXNG (tests/fake_searx.py, port 3997).
Simulated inside the test: the AI and the queue."""
import os
import re
import sys
from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import ai, control, crawl
from app import engines as EN
from app.db import (AppLog, Decision, Group, InboxItem, Job, JobTrace, Keyword, Membership, RejectedKeyword,
                    SearchLog, SessionLocal, User, get_setting, set_setting)

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


def searx(path):
    return httpx.get(SEARX + path, timeout=5).json()


def job(jid):
    with SessionLocal() as s:
        return s.get(Job, jid)


app = __import__("app.main", fromlist=["app"]).app


def client(name, password="secret123"):
    cl = TestClient(app)
    cl.__enter__()
    cl.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    return cl


c = client("admin")
w = client("worker1")      # Researcher: own requests, no crawler settings, doesn't see methods
v = client("viewer1")      # Viewer
surf = client("surfer1")   # Researcher, own contacts only

# ---------- upgrade ----------
check(c.get("/health").json().get("version") == "v0.8", "version v0.8")
with SessionLocal() as s:
    check(s.scalar(select(func.count(SearchLog.id))) == 0, "search_log table made, empty")
    groups = {g.name: g for g in s.scalars(select(Group)).all()}
    admin = s.scalar(select(User).where(User.username == "admin"))
    worker = s.scalar(select(User).where(User.username == "worker1"))
    jobs_before = s.scalar(select(func.count(Job.id)))
man, mat, std, ret = groups["Manufacturers"], groups["Materials"], groups["Standards"], groups["Online retailers"]

# ---------- 2. delete a directory only when it is empty ----------
with SessionLocal() as s:
    man_contacts = s.scalar(select(func.count(Membership.record_id)).where(Membership.group_id == man.id))
    man_waiting = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.group_id == man.id, InboxItem.status == "new"))
    ret_waiting = s.scalars(select(InboxItem.id).where(InboxItem.group_id == ret.id, InboxItem.status == "new")).all()
r = c.get(f"/settings/directories/{man.id}")
check(f"still has <b>{man_contacts} contacts</b>" in r.text and "waiting in the Inbox" in r.text
      and f'href="/d/{man.id}?view=list"' in r.text and f'href="/inbox?dir={man.id}"' in r.text,
      "directory with contacts and Inbox items: both reasons with links")
check('disabled aria-disabled="true"' in r.text and f'action="/settings/directories/{man.id}/delete"' not in r.text,
      "…and the Delete button is switched off")
r = c.post(f"/settings/directories/{man.id}/delete", follow_redirects=True)
with SessionLocal() as s:
    check(s.get(Group, man.id) is not None, "delete is refused on the server too")
check("be deleted: it still has" in r.text and "Move or remove the contacts" in r.text, "refusal message shown")
r = c.get(f"/settings/directories/{ret.id}")
check("still has" not in r.text and "waiting in the Inbox" in r.text, "only Inbox items: only that reason")
c.post(f"/settings/directories/{ret.id}/delete")
with SessionLocal() as s:
    check(s.get(Group, ret.id) is not None, "Inbox items alone also block deleting")
c.post("/inbox/reject", data={"ids": [str(i) for i in ret_waiting], "reason": "Off-topic"})
r = c.get(f"/settings/directories/{ret.id}")
check(f'action="/settings/directories/{ret.id}/delete"' in r.text and "This directory is empty" in r.text,
      "after rejecting them: Delete is available")
check(v.post(f"/settings/directories/{ret.id}/delete").status_code == 403, "a Viewer can't delete directories")
c.post(f"/settings/directories/{ret.id}/delete")
with SessionLocal() as s:
    check(s.get(Group, ret.id) is None, "empty directory deleted")
    check(s.scalar(select(func.count(Decision.id)).where(Decision.decision == "reject")) > 0,
          "decisions are kept (training data)")
c.post(f"/settings/directories/{std.id}/delete")
with SessionLocal() as s:
    check(s.get(Group, std.id) is None, "a directory that never had anything deletes straight away")

# ---------- 9. contact cards fill the row ----------
r = c.get(f"/d/{man.id}?view=grid")
grid = re.search(r'<div class="grid cards[^"]*"[^>]*>', r.text).group(0)
check(" fill" in grid and "max-width" not in grid, f"Fill the row is on by default {grid}")
c.post("/settings/display", data={"mode": "fixed", "px": "1280", "pct": "90", "view": "grid", "per_row": "3",
                                  "card_style": "A", "card_width": "260", "card_tint": "on", "card_fill": "on",
                                  "scope": "everyone"})
grid = re.search(r'<div class="grid cards[^"]*"[^>]*>', c.get(f"/d/{man.id}").text).group(0)
check("rowcap" in grid and "--perrow:3" in grid and "max-width" not in grid, "fill + at most 3 per row share the width")
c.post(f"/settings/directories/{man.id}", data={"section": "cards", "card_style": "B", "card_width": "300",
                                                 "card_tint": "", "card_fill": "off"})
with SessionLocal() as s:
    check(s.get(Group, man.id).card.get("fill") is False, "directory: Fill the row off saved")
grid = re.search(r'<div class="grid cards[^"]*"[^>]*>', c.get(f"/d/{man.id}").text).group(0)
check(" fill" not in grid and "max-width:924px" in grid and "--cardw:300px" in grid,
      "fill off: exact width, 3 per row = fixed maximum width (as in v0.7)")
check('name="card_fill"' in c.get(f"/settings/directories/{man.id}").text, "Directory Settings → Cards has Fill the row")
c.post(f"/settings/directories/{man.id}", data={"section": "cards", "card_style": "", "card_width": "",
                                                 "card_tint": "", "card_fill": ""})
c.post("/settings/display", data={"mode": "fixed", "px": "1280", "pct": "90", "view": "grid", "per_row": "0",
                                  "card_style": "A", "card_width": "260", "card_tint": "on", "scope": "me"})
grid = re.search(r'<div class="grid cards[^"]*"[^>]*>', c.get(f"/d/{man.id}").text).group(0)
check(" fill" not in grid, "Display for me with Fill the row unticked")
check(" fill" in re.search(r'<div class="grid cards[^"]*"[^>]*>', w.get(f"/d/{man.id}?view=grid").text).group(0),
      "…others keep it (default for everyone)")
check('name="card_fill"' in c.get("/settings/display").text, "Display has Fill the row")

# ---------- 3. search engines ----------
searx("/__reset")
searx("/__block")
EN._config_cache.update(value=None, at=0.0)
r = c.get("/settings/search-engines")
check(r.status_code == 200 and "Google" in r.text and "Bing" in r.text and "DuckDuckGo" in r.text
      and "Brave" in r.text and "Not Used Yet" in r.text, "Search Engines page lists the engines")
check(r.text.count(">default</span>") == 4, "SearXNG's defaults marked (google, bing, duckduckgo, wikipedia)")
check(w.get("/settings/search-engines").status_code == 403, "Researcher can't open Search Engines")
check("/settings/search-engines" in c.get("/settings/crawler").text, "in the Settings menu")

c.post("/jobs", data={"query": "glove makers", "group_id": str(man.id)})
with SessionLocal() as s:
    j1 = s.scalar(select(Job).order_by(Job.id.desc()).limit(1))
run_queued()
calls = searx("/__calls")
check(calls and calls[0]["engines"] is None, "no choice saved: SearXNG chooses (no engines= sent)")
check(job(j1.id).status == "done" and job(j1.id).saved >= 1, f"discovery through SearXNG works ({job(j1.id).message})")
with SessionLocal() as s:
    logs = s.scalars(select(SearchLog).where(SearchLog.job_id == j1.id).order_by(SearchLog.id)).all()
    tr = s.scalars(select(JobTrace).where(JobTrace.job_id == j1.id, JobTrace.kind == "search")
                   .order_by(JobTrace.id)).all()
check(logs and logs[0].results.get("bing") == 2 and logs[0].results.get("google") == 1 and not logs[0].errors
      and logs[0].asked == ["google", "bing", "duckduckgo", "wikipedia"], "each search logged: links per engine")
check(tr and sorted(tr[0].data["engines"]["http://dir.test/list"]) == ["bing", "google"],
      "Debug trace: which engines gave each link")
r = c.get(f"/requests/{j1.id}/debug")
check('<span class="engb">Bing</span>' in r.text and '<span class="engb">Google</span>' in r.text,
      "Debug page shows the engine of each link")
r = c.get("/settings/search-engines")
row_g = r.text.split("<b>Google</b>")[1].split("</tr>")[0]
check("Working" in row_g and "link" in row_g, "Google: Working, with its links counted")

searx("/__block?google=CAPTCHA")
c.post("/jobs", data={"query": "glove makers pakistan", "group_id": str(man.id)})
with SessionLocal() as s:
    j2 = s.scalar(select(Job).order_by(Job.id.desc()).limit(1))
run_queued()
with SessionLocal() as s:
    log2 = s.scalars(select(SearchLog).where(SearchLog.job_id == j2.id)).first()
    first_fail = s.scalar(select(func.min(SearchLog.at)).where(SearchLog.job_id == j2.id))
check(log2 and log2.errors.get("google") == "CAPTCHA" and "google" not in log2.results, "CAPTCHA logged as failed")
with SessionLocal() as s:
    st = EN.status(s, ["google", "bing"])
check(st["google"]["state"] == "blocking" and st["google"]["since"] == first_fail and st["bing"]["state"] == "working",
      "Google: Blocking since its first failed search; Bing still working")
r = c.get("/settings/search-engines")
row_g = r.text.split("<b>Google</b>")[1].split("</tr>")[0]
check("Blocking" in row_g and "started" in row_g and "CAPTCHA" in row_g, "page: Blocking, since when, reason")
r = c.get("/")
check("Google is blocking searches (CAPTCHA) — started" in r.text and 'href="/settings/search-engines"' in r.text,
      "Dashboard: Needs Attention warns, with a button")
check("Google is blocking searches" in w.get("/").text and 'href="/settings/search-engines"' not in w.get("/").text,
      "…a Researcher sees the warning without the settings button")
check("1 engine blocking" in c.get("/dashboard/system").text, "System status: search engine online · 1 blocking")
r = c.get(f"/requests/{j2.id}/debug")
check("failed: Google" in r.text and "Engines that failed: Google (CAPTCHA)" in r.text, "Debug shows the failed engine")

r = c.post("/settings/search-engines", data={"on": ["bing", "duckduckgo"]}, follow_redirects=False)
with SessionLocal() as s:
    check(get_setting(s, "search_engines") == {"set": True, "on": ["bing", "duckduckgo"]}, "choice saved")
check(EN.chosen() == ["bing", "duckduckgo"], "searches now use the chosen engines")
check("Google is blocking" not in c.get("/").text, "a switched-off engine no longer warns on the Dashboard")
searx("/__reset")
c.post("/jobs", data={"query": "glove makers lahore", "group_id": str(man.id)})
run_queued()
calls = searx("/__calls")
check(calls and all(x["engines"] == "bing,duckduckgo" for x in calls), "engines=bing,duckduckgo sent to SearXNG")
r = c.post("/settings/search-engines", data={}, follow_redirects=True)
with SessionLocal() as s:
    check(get_setting(s, "search_engines")["on"] == ["bing", "duckduckgo"] and "at least one" in r.text,
          "switching every engine off is refused")
c.post("/settings/search-engines", data={"on": ["bing", "duckduckgo", "google", "nonsense"]})
with SessionLocal() as s:
    check(get_setting(s, "search_engines")["on"] == ["bing", "duckduckgo", "google"], "unknown engine names ignored")
r = c.post("/settings/search-engines/test", data={"query": "glove makers"})
check(r.status_code == 200 and "Test: 2 results" in r.text and "Test: CAPTCHA" in r.text,
      "Test Now asks each engine: Bing 2 results, Google CAPTCHA")
with SessionLocal() as s:
    tests = s.scalars(select(SearchLog).where(SearchLog.test)).all()
check(len(tests) == 3 and all(len(t.asked) == 1 for t in tests), "each engine tested on its own (logged as test)")
searx("/__block")
c.post("/settings/search-engines/test", data={"query": "glove makers"})
with SessionLocal() as s:
    st = EN.status(s, ["google"])
check(st["google"]["state"] == "working" and st["google"]["since"] is None, "Google works again → Working")
c.post("/settings/search-engines", data={"action": "reset"})
with SessionLocal() as s:
    check(not get_setting(s, "search_engines"), "Use SearXNG's Defaults clears the choice")
check(EN.chosen() is None, "…and searches go back to SearXNG's own choice")
with SessionLocal() as s:
    s.add(SearchLog(query="old", at=datetime.utcnow() - timedelta(days=40), results={}, errors={}, asked=[]))
    s.commit()
    control.purge_deleted(s)
    s.commit()
    check(not s.scalar(select(SearchLog).where(SearchLog.query == "old")), "search log kept 30 days")

# ---------- 6. Edit and Run Again ----------
w.post("/jobs", data={"query": "nothing here", "group_id": str(man.id)})
with SessionLocal() as s:
    wj = s.scalar(select(Job).where(Job.user_id == worker.id).order_by(Job.id.desc()).limit(1))
run_queued()
check(job(wj.id).status == "done" and job(wj.id).saved == 0, "a search that finds nothing")
r = w.get("/requests")
row = r.text.split(f"#{wj.id} ·")[1].split("</tr>")[0]
check("Nothing found — try different words or Go Deeper." in row and f'href="/requests/{wj.id}/edit"' in row,
      "Requests: nothing-found hint with Edit and Run Again")
check(">Edit</a>" in row and "Run Again" in row, "Edit and plain Run Again both offered")
r = w.get(f"/requests/{wj.id}/edit")
check(r.status_code == 200 and 'name="query"' in r.text and "Nothing found" in r.text and "Go Deeper and Run (Level 1)" in r.text,
      "edit page: form, hint, Go Deeper")
check("Search methods (" not in r.text, "a person who doesn't see search methods isn't offered them")
check(surf.get(f"/requests/{wj.id}/edit").status_code == 403, "someone else can't edit it without Control everyone's")
check(v.get(f"/requests/{wj.id}/edit").status_code == 403, "a Viewer can't edit requests")
with SessionLocal() as s:
    s.add(RejectedKeyword(text="bad words", norm=control.norm_keyword("bad words"), group_id=None, reason="test"))
    s.commit()
r = w.post(f"/requests/{wj.id}/edit", data={"query": "bad words", "group_id": str(man.id)}, follow_redirects=True)
check(job(wj.id).query == "nothing here" and "reject list" in r.text, "a rejected keyword can't be run by editing")
searx("/__reset")
r = w.post(f"/requests/{wj.id}/edit", data={"query": "glove exporters pk", "group_id": str(man.id), "depth": "0",
                                            "go_deeper": "1"}, follow_redirects=False)
jj = job(wj.id)
check(jj.status == "queued" and jj.query == "glove exporters pk" and jj.params.get("try") == 2
      and jj.params.get("deeper") == 1 and jj.saved == 0 and jj.started_at is None, "same request queued as try 2, Go Deeper 1")
check(jj.params["tries"][0]["query"] == "nothing here" and jj.params["tries"][0]["n"] == 1
      and jj.params["tries"][0]["status"] == "done", "try 1 kept in the history")
run_queued()
jj = job(wj.id)
calls = searx("/__calls")
check(jj.status == "done" and jj.saved >= 0 and max(x["pageno"] for x in calls) >= 3,
      f"try 2 ran deeper (result pages up to {max(x['pageno'] for x in calls)})")
with SessionLocal() as s:
    check(s.scalar(select(func.count(Job.id))) == jobs_before + 4, "no new request was made (edits stay in the request)")
    note = s.scalar(select(JobTrace).where(JobTrace.job_id == wj.id, JobTrace.kind == "note"))
check(note and "Try 2" in note.data.get("text", ""), "Debug: where try 2 starts")
r = w.get("/requests")
check(f'href="/requests/{wj.id}/edit" class="trybadge"' in r.text and ">Try 2</a>" in r.text, "Requests: Try 2 badge")
r = w.get(f"/requests/{wj.id}/edit")
check("nothing here" in r.text and "Level 1" in r.text and "Try 2" in r.text, "Tries list on the page")
w.post(f"/requests/{wj.id}/edit", data={"query": "glove exporters pk", "group_id": str(mat.id), "depth": "0"})
jj = job(wj.id)
check(jj.group_id == mat.id and jj.params.get("try") == 3 and jj.params.get("deeper") == 0, "try 3 in another directory")
r = w.post(f"/requests/{wj.id}/edit", data={"query": "anything", "group_id": str(man.id)}, follow_redirects=True)
check(job(wj.id).query == "glove exporters pk" and "can be changed when it has finished" in r.text,
      "a waiting request can't be edited")
run_queued()
jj = job(wj.id)
check(len(jj.params["tries"]) == 2 and jj.status == "done" and jj.saved >= 1,
      f"three tries: two in the history + the current, which found {jj.saved}")
with SessionLocal() as s:
    items = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.job_id == wj.id))
check(items >= 1, f"Inbox items of all tries stay linked to the request ({items})")
r = w.get(f"/requests/{wj.id}/edit")
row1 = r.text.split("<b>nothing here</b>")[1].split("</tr>")[0]
row3 = r.text.split("(now)")[1].split("</tr>")[0]
check("Save as Keyword" in row3 and "Save as Keyword" not in row1, "Save as Keyword offered on a try that found something")
r = w.post(f"/requests/{wj.id}/save-keyword", data={"n": "1"}, follow_redirects=True)
with SessionLocal() as s:
    check(not s.scalar(select(Keyword).where(Keyword.text == "nothing here")) and "found nothing" in r.text,
          "a try that found nothing isn't saved as a keyword")
w.post(f"/requests/{wj.id}/save-keyword", data={"n": "3"})
with SessionLocal() as s:
    kw = s.scalar(select(Keyword).where(Keyword.group_id == mat.id, Keyword.text == "glove exporters pk"))
check(kw is not None and kw.night and kw.method == "all" and kw.found_count == jj.saved,
      "Save as Keyword adds it to that try's directory's keywords")
r = w.post(f"/requests/{wj.id}/save-keyword", data={"n": "3"}, follow_redirects=True)
with SessionLocal() as s:
    check(s.scalar(select(func.count(Keyword.id)).where(Keyword.group_id == mat.id, Keyword.text == "glove exporters pk")) == 1
          and "already a keyword" in r.text, "saving again doesn't make a second keyword")

# a keyword request whose text is changed is no longer that keyword's run
with SessionLocal() as s:
    kw_id = s.scalar(select(Keyword.id).where(Keyword.group_id == mat.id, Keyword.text == "glove exporters pk"))
c.post(f"/groups/{mat.id}/keywords/{kw_id}/run")
with SessionLocal() as s:
    kj = s.scalar(select(Job).where(Job.kind == "keyword").order_by(Job.id.desc()).limit(1))
run_queued()
with SessionLocal() as s:
    count_before = s.get(Keyword, kw_id).found_count
c.post(f"/requests/{kj.id}/edit", data={"query": "glove makers sialkot", "group_id": str(mat.id), "methods": ["web"]})
kj2 = job(kj.id)
check(kj2.kind == "request" and "keyword_id" not in kj2.params and kj2.params.get("methods") == ["web"],
      "changed keyword run becomes a normal request; methods chosen by someone who sees them")
run_queued()
with SessionLocal() as s:
    check(s.get(Keyword, kw_id).found_count == count_before, "…so the keyword's count isn't changed")
# plain Run Again keeps the methods
c.post(f"/requests/{kj.id}/again")
with SessionLocal() as s:
    nj = s.scalar(select(Job).order_by(Job.id.desc()).limit(1))
check(nj.id != kj.id and nj.params.get("methods") == ["web"] and "tries" not in nj.params,
      "plain Run Again: a new request with the same methods, no tries")
run_queued()
with SessionLocal() as s:
    ej = s.scalar(select(Job).where(Job.kind == "enrich").limit(1))
check(c.get(f"/requests/{ej.id}/edit", follow_redirects=False).status_code == 303, "Enrich requests can't be edited")

# ---------- help & handbook ----------
r = c.get("/help/search-engines")
check(r.status_code == 200 and "Blocking" in r.text, "help page: Search engines")
check(w.get("/help/search-engines", follow_redirects=False).status_code == 303, "…only for people with Crawler settings")
check("Edit and Run Again" in c.get("/help/requests").text, "help: Edit and Run Again")
check("only be deleted when it is" in c.get("/help/directory-settings").text, "help: deleting only empty directories")
check("Fill the row" in c.get("/help/directory-settings").text, "help: Fill the row")
r = c.get("/help/whats-new")
check("v0.8" in r.text, "What's New has v0.8")
from app import handbook
missing = [f for f in handbook.FEATURES if not os.path.exists(os.path.join("docs", "dev", "features", f + ".md"))]
check(not missing, f"every feature has a Handbook page {missing}")
check("/settings/search-engines" in c.get("/dev/handbook/auto-routes").text, "Handbook addresses list the new page")
check("search_log" in c.get("/dev/handbook/auto-database").text, "Handbook tables list search_log")

for page in ["/", "/requests", "/inbox", "/contacts", f"/d/{man.id}", "/directories", "/settings/display",
             "/settings/search-engines", f"/settings/directories/{mat.id}", f"/requests/{wj.id}/edit",
             f"/requests/{wj.id}/debug"]:
    check(c.get(page).status_code == 200, f"opens: {page}")
with SessionLocal() as s:
    errs = s.scalars(select(AppLog).where(AppLog.level == "error", AppLog.at >= datetime.utcnow() - timedelta(hours=1))).all()
check(not errs, "no errors in the log " + "; ".join(e.message for e in errs[:3]))

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("ALL PASSED")
