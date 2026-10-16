"""End-to-end test of NetGate v0.5 on a database upgraded from v0.4.
Real: Postgres, local web pages, headless browser. Simulated: search engine, AI, eBay API (local fake)."""
import io
import json
import re
import sys
import time

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import ai, control, crawl, jobs, learn
from app.db import (Decision, Group, InboxItem, Job, JobTrace, Keyword, Membership, Record, RejectedKeyword, Role,
                    SessionLocal, User, get_setting, init_db, set_setting)

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


SEARCHES = []


def fake_search(q, pageno=1):
    SEARCHES.append(q)
    if q.startswith('"'):
        name = q.split('"')[1]
        if "site:" in q:
            return []
        if name.startswith("Beta"):
            return [{"url": "http://beta.test/", "title": "Beta Gloves official", "content": "Beta Gloves Sialkot"}]
        return []
    if "site:dir.test" in q:
        return [{"url": "http://dir.test/list", "title": "Glove makers directory", "content": ""}]
    if pageno == 1 and "list" not in q and "top" not in q:
        return [{"url": "http://dir.test/list", "title": "Glove makers directory", "content": ""},
                {"url": "http://jsdir.test/top", "title": "Top makers", "content": ""}]
    return []


LINE = re.compile(r"([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2}) — ([A-Za-z]+), ([A-Za-z]+)")
AI = []


def fake_ask(job_type, prompt, timeout=300):
    AI.append((job_type, prompt))
    if "help pages below" in prompt:
        return {"answer": "Open Requests and press Pause or Stop on the request.", "pages": ["requests"]}
    if "List every" in prompt:
        text = prompt.split("Page text:", 1)[1]
        return {"entries": [{"name": n, "city": c, "country": k, "website": None, "description": f"{n} makes gloves.",
                             "fields": {}} for n, c, k in LINE.findall(text)]}
    if "120 workers" in prompt:
        return {"same_company": True, "description": "Acme Leather makes leather gloves and jackets since 1990.",
                "fields": {"employees": "51–200", "products": ["leather gloves", "jackets"]}}
    return {"same_company": True, "fields": {}}


crawl.search = fake_search
ai.ask_json = fake_ask
import rq  # stub: records enqueue calls
QCALLS = rq.CALLS


def run_queued():
    """Run what the web pages queued (the stub queue only records calls)."""
    n = 0
    while QCALLS:
        name, func_, args, kwargs = QCALLS.pop(0)
        kwargs = {k: v for k, v in kwargs.items() if k != "job_timeout"}
        if isinstance(func_, str):
            mod, fn = func_.rsplit(".", 1)
            func_ = getattr(__import__(mod, fromlist=[fn]), fn)
        func_(*args, **kwargs)
        n += 1
    return n


def run_job_now(jid):
    jobs.run_job(jid)


def job(jid):
    with SessionLocal() as s:
        return s.get(Job, jid)


# ---------- upgrade from v0.4 ----------
init_db(); init_db()
with SessionLocal() as s:
    manu = s.scalar(select(Group).where(Group.name == "Manufacturers"))
    mats = s.scalar(select(Group).where(Group.name == "Materials"))
    gid, mid = manu.id, mats.id
    roles = {r.name: r for r in s.scalars(select(Role)).all()}
    users = {u.username: u for u in s.scalars(select(User)).all()}
    check(set(roles) == {"Admin", "Manager", "Researcher", "Viewer", "Developer"}, f"roles seeded: {sorted(roles)}")
    check(users["admin"].role == "Admin" and users["admin"].is_admin, "admin → Admin role")
    check(users["worker1"].role == "Researcher" and "review" in users["worker1"].perm_set
          and "requests_own" in users["worker1"].perm_set, "v0.4 Editor → Researcher with same access + new keys")
    check(users["viewer1"].role == "Viewer" and users["viewer1"].custom and "delete" in users["viewer1"].perm_set
          and "export" in users["viewer1"].perm_set and "edit" not in users["viewer1"].perm_set,
          "custom v0.4 user keeps exact access (exceptions)")
    check(s.scalar(select(func.count(Membership.record_id))) == 5, "every v0.4 listing is an accepted member")
    check(all(r.accepted_at and r.history for r in s.scalars(select(Record)).all()), "records accepted with history note")
    check(manu.methods == {"web": {}, "website": {}}, "groups became directories with web + website methods")
    set_setting(s, "crawler", {"delay": 0.2})
    s.commit()
crawl._settings_cache["value"] = None

c = TestClient(app := __import__("app.main", fromlist=["app"]).app)
c.post("/login", data={"username": "admin", "password": "secret123"})

# ---------- Discover → Inbox ----------
with SessionLocal() as s:
    j = Job(query="glove makers", group_id=gid, kind="keyword", user_id=users["admin"].id, stats={}, params={})
    s.add(j); s.commit(); jid = j.id
run_job_now(jid)
jb = job(jid)
print("   discover:", jb.message)
with SessionLocal() as s:
    items = s.scalars(select(InboxItem).where(InboxItem.group_id == gid)).all()
    names = {s.get(Record, i.record_id).title for i in items}
    check(jb.status == "done", "discover finished")
    check({"Beta Gloves", "Delta Wear", "Theta Gear", "Zeta Apparel"} <= names, f"new companies are in the Inbox: {sorted(names)}")
    acme = s.scalar(select(Record).where(Record.name_key == "acme leather"))
    check(not any(s.get(Record, i.record_id).name_key == "acme leather" for i in items),
          "Acme (already accepted) is not put in the Inbox again")
    check(acme.data.get("website") == "http://acme.test/", "…but its gaps were filled (website from profile)")
    check(s.scalar(select(func.count(Membership.record_id)).where(Membership.group_id == gid)) == 4,
          "nothing reached the directory without being accepted")
    check(all(i.method == "web" and i.keyword == "glove makers" for i in items), "items know method + keyword")
    check(jb.saved == len(items), f"stats count new Inbox items ({jb.saved})")
    beta = s.scalar(select(Record).where(Record.title == "Beta Gloves"))
    check(any("Found by Web search" in h["text"] for h in beta.history), "history note on the contact")
    traces = s.scalar(select(func.count(JobTrace.id)).where(JobTrace.job_id == jid))
    kinds = set(s.scalars(select(JobTrace.kind).where(JobTrace.job_id == jid)).all())
    check(traces > 5 and {"search", "page", "ai", "code"} <= kinds, f"debug trace recorded ({traces} rows, {sorted(kinds)})")
    item_of = {s.get(Record, i.record_id).title: i.id for i in items}

r = c.get("/inbox")
check(r.status_code == 200 and "Beta Gloves" in r.text and "Delta Wear" in r.text, "Inbox page lists them")
open("/var/tmp/ng5_inbox.html", "w").write(r.text)
r = c.get(f"/d/{gid}")
check("Beta Gloves" not in r.text and "Acme Leather" in r.text, "directory shows only accepted contacts")

# accept / reject / restore
c.post("/inbox/accept", data={"ids": [item_of["Beta Gloves"], item_of["Theta Gear"]]})
c.post("/inbox/reject", data={"ids": [item_of["Delta Wear"]], "reason": "Trader, not manufacturer"})
c.post("/inbox/accept", data={"ids": [item_of["Zeta Apparel"]], "group_id": str(mid)})
with SessionLocal() as s:
    beta = s.scalar(select(Record).where(Record.title == "Beta Gloves"))
    zeta = s.scalar(select(Record).where(Record.title == "Zeta Apparel"))
    check(s.get(Membership, (beta.id, gid)) is not None, "accept puts Beta into Manufacturers")
    check(s.get(Membership, (zeta.id, mid)) is not None and s.get(Membership, (zeta.id, gid)) is None,
          "accept into another directory (Zeta → Materials)")
    check(s.get(InboxItem, item_of["Delta Wear"]).status == "rejected"
          and s.get(InboxItem, item_of["Delta Wear"]).reason == "Trader, not manufacturer", "reject with reason")
    dec = s.scalars(select(Decision)).all()
    check(len([d for d in dec if d.decision == "accept"]) == 3 and len([d for d in dec if d.decision == "reject"]) == 1,
          "every decision is logged")
r = c.get("/inbox?tab=rejected")
check("Delta Wear" in r.text and "Trader, not manufacturer" in r.text, "Rejected tab = restore list")
c.post("/inbox/restore", data={"ids": [item_of["Delta Wear"]]})
with SessionLocal() as s:
    check(s.get(InboxItem, item_of["Delta Wear"]).status == "new", "restore puts it back in the Inbox")
c.post("/inbox/reject", data={"ids": [item_of["Delta Wear"]], "reason": "Trader, not manufacturer"})
r = c.get(f"/d/{gid}")
check("Beta Gloves" in r.text, "accepted contact appears in the directory")

# one record in several directories
c.post(f"/records/{beta.id}/directories", data={"group_id": mid})
r = c.get("/contacts?view=list")
with SessionLocal() as s:
    check(s.get(Membership, (beta.id, mid)) is not None, "add an accepted contact to a second directory")
    check(s.scalar(select(func.count(Record.id)).where(Record.title == "Beta Gloves")) == 1, "…still one record")
check("Manufacturers" in r.text and "Materials" in r.text and "Beta Gloves" in r.text, "All contacts shows its directories")
r = c.get(f"/records/{beta.id}/open")
check("Remove from Materials" in r.text and "History" in r.text, "card shows directories + history")

# rediscover: rejected stays rejected, accepted not re-added
before = None
with SessionLocal() as s:
    before = s.scalar(select(func.count(InboxItem.id)).where(InboxItem.status == "new"))
    j = Job(query="glove makers", group_id=gid, kind="keyword", user_id=users["admin"].id, stats={}, params={})
    s.add(j); s.commit(); jid2 = j.id
run_job_now(jid2)
with SessionLocal() as s:
    delta_items = s.scalars(select(InboxItem).join(Record, Record.id == InboxItem.record_id)
                            .where(Record.title == "Delta Wear")).all()
    check(len(delta_items) == 1 and delta_items[0].status == "rejected", "a rejected company is skipped by the next search")
    check(s.scalar(select(func.count(InboxItem.id)).where(InboxItem.status == "new")) == before,
          "second identical search adds nothing new to the Inbox")

# ---------- suggestions (learning) ----------
with SessionLocal() as s:
    for name, summary in [("Sigma Gloves", "Sigma makes leather gloves in Sialkot"), ("Omega Gloves", "Omega makes leather gloves for bikers"),
                          ("Lambda Traders", "Lambda Traders resell garments, trading company, not a manufacturer")]:
        rec = Record(title=name, topic="t", summary=summary, facts="", data={"city": "Sialkot", "country": "Pakistan"},
                     sources={}, social={}, source_url="", name_key=name.lower())
        s.add(rec); s.flush()
        s.add(InboxItem(record_id=rec.id, group_id=gid, status="new", method="web", keyword="gloves"))
    # traders the user rejected before
    from app import contacts as C
    admin_u = s.get(User, users["admin"].id)
    for name in ["Chi Traders", "Psi Trading Co", "Nu Garment Traders"]:
        rec = Record(title=name, topic="t", summary=f"{name} resell garments and gloves, a trading company, not a manufacturer",
                     facts="", data={"city": "Karachi", "country": "Pakistan"}, sources={}, social={}, source_url="", name_key=name.lower())
        s.add(rec); s.flush()
        it = InboxItem(record_id=rec.id, group_id=gid, status="new", method="web", keyword="gloves")
        s.add(it); s.flush()
        C.reject(s, it, admin_u, "Trader, not manufacturer")
    # a few more decisions so there is history
    for name in ["Kappa Leathers", "Iota Moto"]:
        it = s.scalar(select(InboxItem).join(Record, Record.id == InboxItem.record_id).where(Record.title == name))
        if it:
            from app import contacts as C
            C.reject(s, it, s.get(User, users["admin"].id), "Trader, not manufacturer") if name == "Iota Moto" else C.accept(s, it, s.get(User, users["admin"].id))
    s.commit()
learn.rescore_group(gid)
with SessionLocal() as s:
    sig = s.scalar(select(InboxItem).join(Record, Record.id == InboxItem.record_id).where(Record.title == "Sigma Gloves"))
    lam = s.scalar(select(InboxItem).join(Record, Record.id == InboxItem.record_id).where(Record.title == "Lambda Traders"))
    print("   suggestions:", sig.suggest, sig.score, sig.why, "|", lam.suggest, lam.score, lam.why)
    check(sig.suggest == "accept" and sig.score and "accepted" in sig.why, "suggests accept for one like accepted ones")
    check(lam.suggest == "reject" and "trader" in lam.why, "suggests reject (with the usual reason) for a trader")
r = c.get("/inbox?sort=score")
check("% " in r.text or "%</span>" in r.text, "Inbox shows AI suggestion %")
r = c.get("/dev/training.jsonl")
lines = [json.loads(x) for x in r.text.strip().splitlines()]
with SessionLocal() as s:
    nd = s.scalar(select(func.count(Decision.id)).where(Decision.decision.in_(["accept", "reject"])))
check(len(lines) == nd and lines[0]["messages"][2]["role"] == "assistant", f"training export: {len(lines)} examples")

# ---------- eBay search method ----------
r = c.post("/settings/directories", data={
    "name": "Online retailers", "description": "Shops selling motorcycle apparel online", "m_ebay": "on", "m_website": "on",
    "ebay_sites": ["EBAY_GB", "EBAY_DE"], "ebay_per_keyword": "200", "ebay_max_sellers": "20", "ebay_min_feedback": "0",
    "ebay_business_only": "on", "presets": ["city", "country", "website", "contact_email", "phone", "sells_on", "seller_rating",
                                             "feedback_count", "business_name"],
    "instructions": "Shops that sell motorcycle jackets.", "keywords": "leather motorcycle jacket", "night": "on"},
    follow_redirects=False)
with SessionLocal() as s:
    ret = s.scalar(select(Group).where(Group.name == "Online retailers"))
    rid_ = ret.id
    check(set(ret.methods) == {"ebay", "website"} and ret.methods["ebay"]["sites"] == ["EBAY_GB", "EBAY_DE"],
          "new directory with eBay method + options")
    srcs = {f.key: f.source for f in ret.fields}
    check(srcs.get("seller_rating") == "ebay:feedback_pct" and srcs.get("sells_on") == "method:marketplace",
          "“Filled from” set for eBay fields")
    kw = ret.keywords[0]
    kid = kw.id
# without keys: skipped with a note
c.post(f"/groups/{rid_}/keywords/{kid}/run")
run_queued()
with SessionLocal() as s:
    last = s.scalars(select(Job).order_by(Job.id.desc())).first()
    check("eBay keys are not set up yet" in (last.message or ""), f"no keys → clear note ({last.message})")
c.post("/settings/connections", data={"ebay_client_id": "APPID", "ebay_client_secret": "CERT", "ebay_sites": ["EBAY_GB"],
                                      "ebay_business_only": "on", "test": "ebay"})
r = c.get("/settings/connections")
check("CERT" not in r.text, "secret never shown")
c.post(f"/groups/{rid_}/keywords/{kid}/run")
run_queued()
with SessionLocal() as s:
    last = s.scalars(select(Job).order_by(Job.id.desc())).first()
    print("   ebay:", last.message)
    its = s.scalars(select(InboxItem).where(InboxItem.group_id == rid_)).all()
    recs = {s.get(Record, i.record_id).title: s.get(Record, i.record_id) for i in its}
    check({"Rider Store Ltd", "Moto Gear Direct", "Motoshop GmbH"} <= set(recs), f"eBay sellers in the Inbox: {sorted(recs)}")
    check(not any("joe" in n.lower() for n in recs), "private seller skipped (business only)")
    rs = recs.get("Rider Store Ltd")
    if rs:
        d = rs.data
        check(d.get("seller_rating") == "99.2%" and d.get("feedback_count") == 4210.0 and d.get("sells_on") == ["eBay"],
              f"eBay fields filled by mapping: {d}")
        check(d.get("contact_email") == "sales@riderstore.co.uk" and d.get("phone") == "+44 113 555 0101"
              and d.get("city") == "Leeds" and d.get("country") == "United Kingdom", "business details from eBay")
        check(rs.links.get("ebay") == "https://www.ebay.co.uk/usr/rider_store_uk" and rs.ext.get("ebay") == "rider_store_uk",
              "store link + eBay id saved")
    md = recs.get("Motoshop GmbH")
    check(md is not None and md.data.get("country") == "Germany", "DE: business filter not supported → checked per seller")
    check(all(i.method == "ebay" for i in its), "method = eBay search")
calls = httpx.get("http://127.0.0.1:3998/__calls").json()
check(any(c_[0] == "POST" for c_ in calls) and any("EBAY_DE" == (c_[2] if len(c_) > 2 else None) for c_ in calls), "real API calls made (token, both sites)")
# run again: same sellers not duplicated
c.post(f"/groups/{rid_}/keywords/{kid}/run")
run_queued()
with SessionLocal() as s:
    n_rider = s.scalar(select(func.count(Record.id)).where(Record.ext.contains({"ebay": "rider_store_uk"})))
    check(n_rider == 1, "same eBay seller matched by its id, no duplicate")

# ---------- request controls ----------
# pause before it starts
with SessionLocal() as s:
    j = Job(query="glove makers pause test", group_id=gid, kind="request", user_id=users["admin"].id, stats={}, params={"methods": ["web"]})
    s.add(j); s.commit(); pj = j.id
c.post(f"/requests/{pj}/pause")
check(job(pj).status == "paused", "pause a waiting request")
run_job_now(pj)
check(job(pj).status == "paused", "the worker skips a paused request")
# resume and pause in the middle
c.post(f"/requests/{pj}/resume")
check(job(pj).status == "queued" and QCALLS, "resume queues it again")
QCALLS.clear()
crawl.purge_cache(0)
orig_get = crawl.get_page
count = {"n": 0}


def pausing_get(url, use_cache=True):
    count["n"] += 1
    if count["n"] == 2:
        with SessionLocal() as s:
            s.get(Job, pj).control = "pause"
            s.commit()
    return orig_get(url, use_cache)


crawl.get_page = pausing_get
jobs.crawl.get_page = pausing_get
run_job_now(pj)
jp = job(pj)
print("   paused at:", jp.message, "| state:", list(jp.state.keys()))
check(jp.status == "paused" and jp.state.get("web", {}).get("queue"), "pause in the middle saves where it got to")
read_before = jp.stats.get("read", 0)
crawl.get_page = orig_get
jobs.crawl.get_page = orig_get
c.post(f"/requests/{pj}/resume")
run_queued()
jp = job(pj)
print("   resumed:", jp.message)
check(jp.status == "done" and not jp.state, "resume continues and finishes")
check(jp.stats.get("read", 0) > read_before, f"…from where it was (pages read {read_before} → {jp.stats.get('read')})")

# stop in the middle
with SessionLocal() as s:
    j = Job(query="glove makers halt test", group_id=gid, kind="request", user_id=users["admin"].id, stats={}, params={"methods": ["web"]})
    s.add(j); s.commit(); sj = j.id
crawl.purge_cache(0)


def stopping_get(url, use_cache=True):
    with SessionLocal() as s:
        jj = s.get(Job, sj)
        jj.control = "stop"
        s.commit()
    return orig_get(url, use_cache)


jobs.crawl.get_page = stopping_get
run_job_now(sj)
jobs.crawl.get_page = orig_get
print("   stop:", job(sj).status, job(sj).message)
check(job(sj).status == "stopped", "stop in the middle")

# reject → reject list
r = c.post(f"/requests/{sj}/reject", data={"reason": "Wrong results"})
with SessionLocal() as s:
    rk = s.scalar(select(RejectedKeyword).where(RejectedKeyword.norm == control.norm_keyword("glove makers halt test")))
    check(job(sj).status == "rejected" and rk and rk.reason == "Wrong results", "reject puts the keyword on the reject list")
check(control.norm_keyword("Halt Test Glove Makers") == control.norm_keyword("glove maker halt test"),
      "reject match ignores order, capitals, plurals")
r = c.post("/jobs", data={"query": "Glove Makers HALT test", "group_id": gid}, follow_redirects=True)
check("reject list" in r.text, "a rejected keyword can't be searched again")
r = c.post("/jobs", data={"query": "glove makers halt", "group_id": gid}, follow_redirects=True)
check("similar to rejected" in r.text, "a similar keyword gets a warning but runs")
QCALLS.clear()
c.post(f"/requests/{sj}/restore")
with SessionLocal() as s:
    check(not s.scalar(select(RejectedKeyword).where(RejectedKeyword.norm == control.norm_keyword("glove makers halt test")))
          and job(sj).status == "stopped", "restore takes it off the reject list")

# delete: only the request layer
with SessionLocal() as s:
    n_rec = s.scalar(select(func.count(Record.id)))
    linked = s.scalar(select(func.count(Record.id)).where(Record.job_id == jid))
c.post(f"/requests/{jid}/delete")
r = c.get("/requests?tab=deleted")
check(job(jid).deleted_at is not None and "glove makers" in r.text, "delete moves the request to the Deleted tab")
c.post(f"/requests/{jid}/undelete")
check(job(jid).deleted_at is None, "…and can be restored from there")
c.post(f"/requests/{jid}/delete")
with SessionLocal() as s:
    s.get(Job, jid).deleted_at = __import__("datetime").datetime(2020, 1, 1)
    s.commit()
    control.purge_deleted(s, 30); s.commit()
with SessionLocal() as s:
    check(s.get(Job, jid) is None and s.scalar(select(func.count(Record.id))) == n_rec and linked > 0
          and s.scalar(select(func.count(Record.id)).where(Record.job_id == jid)) == 0,
          f"after 30 days the request is gone, all {n_rec} contacts kept (link cleared)")

# bulk + pause all
with SessionLocal() as s:
    ids = []
    for q in ("bulk one", "bulk two"):
        j = Job(query=q, group_id=gid, kind="request", user_id=users["admin"].id, stats={}, params={})
        s.add(j); s.flush(); ids.append(j.id)
    s.commit()
c.post("/requests/pause-all")
check(all(job(i).status == "paused" for i in ids), "Pause all")
c.post("/requests/bulk", data={"ids": ids, "action": "stop"})
check(all(job(i).status == "stopped" for i in ids), "bulk stop")
r = c.get("/requests")
check(r.status_code == 200 and "Run again" in r.text, "Requests page with actions")
open("/var/tmp/ng5_requests.html", "w").write(r.text)
r = c.get(f"/requests/{pj}/debug")
check(r.status_code == 200 and "AI questions" in r.text and "Pages read" in r.text, "debug view")

# ---------- add contact by hand ----------
r = c.get("/contacts/check", params={"name": "Beta Gloves"})
check("possible match" in r.text, "duplicate check finds an existing company")
r = c.get("/contacts/check", params={"name": "Totally New Shop"})
check("No match found" in r.text, "…and says when there is none")
r = c.post("/contacts/add", data={"tab": "one", "name": "New Moto Shop", "country": "United Kingdom",
                                  "links": "https://www.ebay.co.uk/usr/moto_gear_direct\nhttps://instagram.com/newmoto",
                                  "email": "hi@newmoto.co.uk", "notes": "Met at EICMA", "group_id": rid_, "then": "inbox"},
           follow_redirects=False)
with SessionLocal() as s:
    mg = s.scalar(select(Record).where(Record.ext.contains({"ebay": "moto_gear_direct"})))
    check(mg is not None and mg.notes == "Met at EICMA" and mg.social.get("instagram") == "https://instagram.com/newmoto",
          "eBay link matched the existing seller; notes and Instagram added to it")
r = c.post("/contacts/add", data={"tab": "list", "group_id": gid, "then": "inbox",
                                  "list": "Acme Leather, Sialkot, Pakistan\nRho Sports, Sialkot, Pakistan, rho.example\nPi Gloves; Lahore; Pakistan; pi@pigloves.pk"},
           follow_redirects=True)
check("2 new contacts" in r.text and "1 already in NetGate" in r.text, "paste a list: 2 new, 1 matched")
with SessionLocal() as s:
    pi = s.scalar(select(Record).where(Record.title == "Pi Gloves"))
    check(pi and pi.data.get("contact_email") == "pi@pigloves.pk" and pi.data.get("city") == "Lahore", "list columns understood")
    pit = s.scalar(select(InboxItem).where(InboxItem.record_id == pi.id))
    check(pit.method == "manual" and pit.why == "directory chosen when added", "hand-added → Inbox, marked as chosen")
csvdata = "Company,City,Country,Website,Email,Seller rating\nUpsilon Moto,Leeds,United Kingdom,upsilon.example,,98%\nPhi Riders,York,United Kingdom,,phi@phi.example,\n"
r = c.post("/contacts/add", data={"tab": "csv", "group_id": rid_, "then": "enrich", "steps": ["website", "find_site"]},
           files={"file": ("list.csv", csvdata, "text/csv")}, follow_redirects=True)
check("2 new contacts" in r.text and "Enrich has started" in r.text, "CSV import + enrich")
with SessionLocal() as s:
    up = s.scalar(select(Record).where(Record.title == "Upsilon Moto"))
    check(up and up.data.get("seller_rating") == "98%" and up.data.get("website") == "https://upsilon.example",
          "CSV column named like a field is used")
n_enrich = len(QCALLS)
run_queued()
with SessionLocal() as s:
    ej = s.scalars(select(Job).where(Job.kind == "enrich").order_by(Job.id.desc())).first()
    check(n_enrich == 2 and ej.status == "done" and ej.params.get("steps") == ["website", "find_site"], "enrich ran with the chosen steps")
r = c.post("/contacts/add", data={"tab": "one", "name": "Accepted Right Away", "group_id": gid, "then": "inbox",
                                  "accept_now": "on"}, follow_redirects=False)
with SessionLocal() as s:
    ara = s.scalar(select(Record).where(Record.title == "Accepted Right Away"))
    check(ara and s.get(Membership, (ara.id, gid)) is not None, "“Accept straight away” skips the Inbox")

# enrich an eBay contact: store lookup
with SessionLocal() as s:
    j = Job(query="Rider Store Ltd", group_id=rid_, kind="enrich", record_id=recs["Rider Store Ltd"].id,
            user_id=users["admin"].id, stats={}, params={"steps": ["ebay"]})
    rec = s.get(Record, recs["Rider Store Ltd"].id)
    d = dict(rec.data); d.pop("phone", None); rec.data = d
    s.add(j); s.commit(); ej = j.id
run_job_now(ej)
with SessionLocal() as s:
    check(s.get(Record, recs["Rider Store Ltd"].id).data.get("phone") == "+44 113 555 0101", "enrich: eBay store lookup refills phone")

# ---------- edit a contact ----------
r = c.post(f"/records/{beta.id}/edit", data={"title": "Beta Gloves", "summary": "Edited.", "notes": "VIP", "f_phone": "+92 300 0000000",
                                             "f_city": "Sialkot"})
with SessionLocal() as s:
    b = s.get(Record, beta.id)
    check(b.data.get("phone") == "+92 300 0000000" and b.notes == "VIP" and b.sources.get("phone") == "edited by admin",
          "edit a contact by hand (source = who edited)")

# ---------- roles & users ----------
form = {f"name_{roles['Researcher'].id}": "Researcher"}
with SessionLocal() as s:
    for r_ in s.scalars(select(Role)).all():
        if r_.locked:
            continue
        form[f"name_{r_.id}"] = r_.name
        form[f"desc_{r_.id}"] = r_.description
        form[f"dirs_{r_.id}"] = "all"
        for p in r_.perm_set:
            if not (r_.name == "Researcher" and p == "edit"):
                form[f"p_{r_.id}_{p}"] = "on"
c.post("/settings/roles", data=form)
with SessionLocal() as s:
    w = s.scalar(select(User).where(User.username == "worker1"))
    check("edit" not in w.perm_set and "review" in w.perm_set, "changing a role changes everyone with it")
c.post("/settings/users/new", data={"username": "dev1", "password": "secret123", "role_id": roles["Developer"].id,
                                     "customise": "on", "perms": ["view", "debug", "logs", "tester", "dev_help", "review"]})
with SessionLocal() as s:
    d1 = s.scalar(select(User).where(User.username == "dev1"))
    check(d1 and d1.role == "Developer" and "review" in d1.perm_set and "training_export" not in d1.perm_set and d1.custom,
          "per-person exceptions on top of a role (custom)")
r = c.get("/settings/users")
check("custom" in r.text, "custom badge on the user list")
r = c.post(f"/settings/roles/{roles['Developer'].id}/delete", follow_redirects=True)
check("still have the role" in r.text, "a role in use can't be deleted")
c.post("/settings/roles/new", data={"name": "Sales", "copy": roles["Viewer"].id})
with SessionLocal() as s:
    check(s.scalar(select(Role).where(Role.name == "Sales")).perm_set == {"view", "export"}, "new role copied from Viewer")
d = TestClient(app)
d.post("/login", data={"username": "dev1", "password": "secret123"})
check(d.get(f"/requests/{pj}/debug").status_code == 200 and d.get("/settings/users").status_code == 403
      and d.get("/settings/connections").status_code == 403, "Developer: debug yes, users / API keys no")
check(d.get("/dev").status_code == 200 and d.get("/dev/logs").status_code == 200, "Developer tools pages")
v = TestClient(app)
v.post("/login", data={"username": "viewer1", "password": "secret123"})
r = v.get("/inbox")
check(r.status_code == 200 and "Beta Gloves" not in r.text, "limited user only sees Inbox items of their directories")

# ---------- help ----------
r = c.get("/help")
check(r.status_code == 200 and "Ask NetGate" in r.text, "Help Center")
r = c.post("/help/ask", data={"question": "how do I stop a search"})
check("Pause or Stop" in r.text and "/help/requests" in r.text, "Ask NetGate answers from the help pages")
import os
bad = []
for f in os.listdir("app/help"):
    slug = f[:-3]
    rr = c.get(f"/help/{slug}")
    if rr.status_code != 200:
        bad.append(slug)
check(not bad, f"every help page opens ({len(os.listdir('app/help'))} pages){bad}")
r = c.get("/help/inbox?partial=1")
check(r.status_code == 200 and "Open in the Help Center" in r.text, "contextual ? help panel")
r = d.get("/help")
check("developer" in r.text.lower(), "developer sees developer help")
r = v.get("/help/developer")
check(r.status_code in (200, 303) and "How NetGate is built" not in r.text, "viewer doesn't see developer help")
r = c.get("/help/whats-new")
check("Discovery Inbox" in r.text, "What's new from the changelog")

# ---------- night run ----------
with SessionLocal() as s:
    set_setting(s, "night", {"enabled": True, "start": "00:00", "stop": "23:59", "days": [0, 1, 2, 3, 4, 5, 6],
                             "max_companies": 5, "pause": 0, "enrich_inbox": True})
    control.reject_keyword(s, "leather motorcycle jacket", None, "test", None)
    s.commit()
from app import scheduler
QCALLS.clear()
scheduler.tick()
with SessionLocal() as s:
    nj = s.scalars(select(Job).where(Job.kind == "night")).first()
check(nj is not None and QCALLS, "scheduler starts the night run")
run_queued()
with SessionLocal() as s:
    nj = s.get(Job, nj.id)
    print("   night:", nj.message)
    check(nj.status == "done", "night run finished")
    check(not any("leather motorcycle jacket" == q for q in SEARCHES[-50:]), "night run skipped the rejected keyword")

# ---------- pages ----------
for url in ["/", "/inbox", "/inbox?tab=enriched", "/contacts", f"/d/{gid}", f"/d/{rid_}?view=list", "/contacts/add",
            "/requests", "/settings/directories/new", f"/settings/directories/{rid_}", "/settings/roles", "/settings/users",
            "/settings/reject-list", "/settings/night", "/settings/ai", "/help", "/dev"]:
    rr = c.get(url)
    check(rr.status_code == 200, f"GET {url}")
with SessionLocal() as s:
    errs = s.scalars(select(__import__("app.db", fromlist=["AppLog"]).AppLog).where(
        __import__("app.db", fromlist=["AppLog"]).AppLog.level == "error")).all()
    check(not errs, "no errors in the log" + (": " + errs[0].message if errs else ""))

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
