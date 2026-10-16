"""End-to-end test of NetGate v0.6 on a database made by v0.5 (run tests/test_v05.py with the v0.5 code first,
or use any copy of a v0.5 database that has its sample data: users admin / worker1 / viewer1 / dev1, password
secret123). Checks: Dashboard, Directories page, directory switcher, moving contacts, People (users, roles,
login history, password changes)."""
import re
import sys

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import Decision, Group, Job, Login, Membership, Record, Role, SessionLocal, User

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


app = __import__("app.main", fromlist=["app"]).app


def client(name, password="secret123", follow=True):
    cl = TestClient(app, follow_redirects=follow)
    cl.__enter__()   # runs startup (the v0.6 upgrade) the first time
    r = cl.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    return cl, r


c, r = client("admin")
check(r.status_code == 303 and r.headers["location"] == "/", "admin logs in after the upgrade")

with SessionLocal() as s:
    admin = s.scalar(select(User).where(User.username == "admin"))
    check(admin.last_login_at is not None, "upgrade: users have last_login_at (set on login)")
    check(s.scalar(select(func.count(Login.id)).where(Login.username == "admin", Login.ok)) >= 1,
          "login history records the login")
    groups = {g.name: g for g in s.scalars(select(Group)).all()}
    man, mat, buy = groups["Manufacturers"], groups["Materials"], groups["Buyers & brands"]

# ---------- Dashboard ----------
r = c.get("/")
check(r.status_code == 200 and "<h1>Dashboard</h1>" in r.text, "NetGate opens on the Dashboard")
for part in ("Inbox waiting", "Needs attention", "Quick actions", "Recent activity", "All directories →"):
    check(part in r.text, f"Dashboard shows “{part}”")
check('href="/" class="nav-item on"' in r.text, "sidebar: Dashboard item is highlighted")
check('class="nav-item nav-dir' not in r.text and 'href="/directories"' in r.text,
      "sidebar: no directory list, one Directories item")
check(re.search(r"accepted .+ into Manufacturers", r.text) is not None, "activity lists accept decisions")
r = c.get("/dashboard/system")
check(r.status_code == 200 and "Browser (renderer)" in r.text and "running" in r.text, "System status: renderer running")
check("Search engine" in r.text and "offline" in r.text, "System status: unreachable search engine shows offline")
check(c.get("/?group=%d" % man.id, follow_redirects=False).headers.get("location") == f"/d/{man.id}",
      "old v0.4 address /?group= still opens the directory")

v, _ = client("viewer1")
r = v.get("/")
check(r.status_code == 200 and "Materials" in r.text and ">Manufacturers<" not in r.text,
      "limited user's Dashboard only shows their directories")

# ---------- Directories page ----------
r = c.get("/directories?view=grid")
check(r.status_code == 200 and r.text.count('class="dircard"') == len(groups), "Directories page: one card per directory")
check("New directory" in r.text and "waiting in Inbox" in r.text and "% complete" in r.text, "cards show counts and + New directory")
r = c.get("/directories?view=list&sort=contacts")
check(r.status_code == 200 and "<table" in r.text, "Directories list view")
names = re.findall(r'<a href="/d/\d+"><b>([^<]+)</b>', r.text)
check(names and names[0] == "Manufacturers", "sort by most contacts puts Manufacturers first")
r = c.get("/directories")
check('aria-current="page">List' in r.text, "the chosen view is remembered")
r = v.get("/directories")
check("New directory" not in r.text and r.text.count('<a href="/d/') == 1, "viewer: only their directory, no New card")

# ---------- switcher ----------
r = c.get(f"/d/{man.id}")
check('class="dirswitch"' in r.text and "← All directories" in r.text and "▾ Jump to…" in r.text, "directory page has the switcher bar")
check(re.search(rf'href="/d/{man.id}" class="on" aria-current="page">Manufacturers', r.text) is not None,
      "current directory tab is marked")
check(all(f'href="/d/{g.id}"' in r.text for g in groups.values()), "every directory has a tab")
check('class="dirswitch"' not in c.get("/contacts").text, "no switcher on All contacts")

# ---------- moving contacts ----------
with SessionLocal() as s:
    rec = s.scalar(select(Record).where(Record.title == "Kappa Leathers"))
    rid = rec.id
    data_before = dict(rec.data)
    mids = set(s.scalars(select(Membership.group_id).where(Membership.record_id == rid)).all())
check(mids == {man.id}, "Kappa Leathers is in Manufacturers")
r = c.get(f"/records/{rid}/open?from={man.id}")
check("Move here" in r.text and "Also add here" in r.text, "card offers Move here / Also add here")
r = v.get(f"/records/{rid}/open")
check(r.status_code == 403, "viewer can't open a contact outside their directory")

r = c.post(f"/records/{rid}/directories", data={"group_id": buy.id, "from_id": man.id, "action": "move"},
           headers={"referer": f"http://testserver/d/{man.id}"})
check(r.status_code == 200, "Move here works")
with SessionLocal() as s:
    rec = s.get(Record, rid)
    mids = set(s.scalars(select(Membership.group_id).where(Membership.record_id == rid)).all())
    check(mids == {buy.id}, "contact left Manufacturers and is in Buyers & brands")
    check(rec.data == data_before, "its details are unchanged")
    check("Moved from Manufacturers to Buyers & brands by admin" in rec.history[-1]["text"], "history notes the move")
    dec = s.scalar(select(Decision).where(Decision.record_id == rid).order_by(Decision.id.desc()).limit(1))
    check(dec.decision == "move" and dec.group_id == buy.id and "Manufacturers" in dec.reason, "move is recorded as a decision")
r = c.get(f"/d/{buy.id}")
check("Kappa Leathers" in r.text, "contact shows in the new directory")

r = c.post(f"/records/{rid}/directories", data={"group_id": mat.id, "action": "add"})
with SessionLocal() as s:
    mids = set(s.scalars(select(Membership.group_id).where(Membership.record_id == rid)).all())
check(mids == {buy.id, mat.id}, "Also add here keeps it in Buyers & brands too")
r = c.get(f"/records/{rid}/open")
check('name="from_id" aria-label="Move from"' in r.text, "a contact in two directories gets a From choice")

# bulk move: three Manufacturers to Buyers & brands
with SessionLocal() as s:
    ids = [r_.id for r_ in s.scalars(select(Record).join(Membership, Membership.record_id == Record.id)
                                      .where(Membership.group_id == man.id).order_by(Record.id).limit(3)).all()]
r = c.get(f"/d/{man.id}?view=list")
check('id="movedlg"' in r.text and "Move there" in r.text and "Also add there" in r.text, "list view has Move there with a confirm box")
r = c.post("/records/move", data={"ids": [str(i) for i in ids], "group_id": str(buy.id), "from_id": str(man.id)},
           headers={"referer": f"http://testserver/d/{man.id}"})
check(r.status_code == 200 and "3 contacts moved to Buyers &amp; brands" in r.text, "bulk move: 3 moved, message shown")
with SessionLocal() as s:
    left = s.scalar(select(func.count()).select_from(Membership).where(Membership.group_id == man.id,
                                                                        Membership.record_id.in_(ids)))
    there = s.scalar(select(func.count()).select_from(Membership).where(Membership.group_id == buy.id,
                                                                         Membership.record_id.in_(ids)))
check(left == 0 and there == 3, "bulk move changed the directories")
# move from all their directories (All contacts page)
r = c.post("/records/move", data={"ids": [str(rid)], "group_id": str(man.id), "from_id": ""},
           headers={"referer": "http://testserver/contacts"})
with SessionLocal() as s:
    mids = set(s.scalars(select(Membership.group_id).where(Membership.record_id == rid)).all())
check(mids == {man.id}, "“From all their directories” leaves both and joins the target")
r = c.post("/records/move", data={"group_id": str(buy.id)}, headers={"referer": "http://testserver/contacts"})
check("Tick one or more contacts first" in r.text, "bulk move with nothing ticked says so")
w, _ = client("worker1")   # Researcher: no "edit"
check(w.post("/records/move", data={"ids": [str(rid)], "group_id": str(buy.id)}).status_code == 403,
      "a Researcher may not move contacts")

# ---------- People: users ----------
r = c.get("/people", follow_redirects=False)
check(r.status_code == 303 and r.headers["location"] == "/settings/users", "People opens the users list")
r = c.get("/settings/users")
check(r.status_code == 200 and "Last login" in r.text and "worker1" in r.text and "+ Add user" in r.text, "users list")
check("viewer1" not in c.get("/settings/users?q=work").text, "users search")
check('>People</a>' in r.text, "People is in the sidebar")
check(w.get("/settings/users").status_code == 403 and '>People</a>' not in w.get("/").text, "no People for a Researcher")

with SessionLocal() as s:
    researcher = s.scalar(select(Role).where(Role.name == "Researcher"))
r = c.post("/settings/users/new", data={"username": "newbie", "password": "temp12345", "role_id": researcher.id,
                                        "active": "on", "must_change": "on"}, follow_redirects=False)
check(r.status_code == 303, "admin adds a user that must change their password")
n, r = client("newbie", "temp12345")
check(r.headers["location"] == "/account/password", "first login goes to “choose your password”")
check(n.get("/inbox", follow_redirects=False).headers.get("location") == "/account/password",
      "other pages wait until the password is changed")
r = n.post("/account/password", data={"old": "temp12345", "new": "short", "new2": "short"})
check("at least 8" in r.text, "too-short new password refused")
r = n.post("/account/password", data={"old": "temp12345", "new": "mine-123456", "new2": "mine-123456"},
           follow_redirects=False)
check(r.headers.get("location") == "/", "password changed")
check(n.get("/inbox").status_code == 200, "after that the person can work")
_, r = client("newbie", "mine-123456")
check(r.headers["location"] == "/", "logs in with the new password")

with SessionLocal() as s:
    nid = s.scalar(select(User.id).where(User.username == "newbie"))
r = c.post(f"/settings/users/{nid}/password", data={"password": "reset-98765", "must_change": "on"})
check("New password set for newbie" in r.text, "admin resets a password")
check(n.get("/inbox", follow_redirects=False).headers.get("location") == "/login",
      "after a reset the person is logged out everywhere")
_, r = client("newbie", "mine-123456")
check(r.status_code == 401, "old password no longer works")
n, r = client("newbie", "reset-98765")
check(r.headers["location"] == "/account/password", "temporary password must be changed again")

r = c.post(f"/settings/users/{nid}", data={"username": "newbie", "role_id": researcher.id, "access": "all"})
with SessionLocal() as s:
    check(s.get(User, nid).active is False, "unticking Active disables the user")
_, r = client("newbie", "reset-98765")
check(r.status_code == 401 and "switched off" in r.text, "disabled user can't log in and is told why")
_, r = client("newbie", "wrong-pass")
with SessionLocal() as s:
    notes = [l.note for l in s.scalars(select(Login).where(Login.username == "newbie").order_by(Login.id)).all()]
check("disabled" in notes and "wrong password" in notes, "login history records failed attempts and why")
r = c.get(f"/settings/logins?user_id={nid}&failed=1")
check(r.status_code == 200 and "Wrong password" in r.text, "Login history page with filters")
r = c.get(f"/settings/users/{nid}")
check("Recent logins" in r.text and "Delete user" in r.text and "Reset password" in r.text, "user page: reset, logins, delete")

# delete
with SessionLocal() as s:
    s.add(Job(query="newbie search", kind="request", user_id=nid, status="done", stats={}, params={}))
    s.add(Decision(user_id=nid, record_id=rid, group_id=man.id, decision="accept", snapshot={"title": "Kappa Leathers"}))
    s.commit()
    admin_id = s.scalar(select(User.id).where(User.username == "admin"))
r = c.post(f"/settings/users/{nid}/delete", data={"confirm": "wrong"})
check("to confirm" in r.text, "delete needs the username typed")
r = c.post(f"/settings/users/{nid}/delete", data={"confirm": "newbie"})
check("deleted" in r.text, "user deleted")
with SessionLocal() as s:
    check(s.get(User, nid) is None, "user is gone")
    check(s.scalar(select(func.count(Job.id)).where(Job.query == "newbie search", Job.user_id.is_(None))) == 1,
          "their request is kept (without owner)")
    check(s.scalar(select(func.count(Login.id)).where(Login.user_id == nid)) > 0, "their login history is kept")
check("(deleted user) accepted" in c.get("/").text, "activity shows “(deleted user)”")
r = c.post(f"/settings/users/{admin_id}/delete", data={"confirm": "admin"})
check("delete your own account" in r.text, "can't delete yourself")
r = c.post(f"/settings/users/{admin_id}", data={"username": "admin", "role_id": researcher.id, "active": "on"})
check("last active admin" in r.text, "last admin keeps the Admin role")

# ---------- People: roles ----------
r = c.post("/settings/roles/new", data={"name": "Buyers team", "copy": str(researcher.id)})
check("created as a copy of Researcher" in r.text, "copy a role")
with SessionLocal() as s:
    sales = s.scalar(select(Role).where(Role.name == "Buyers team"))
    check(sales and sales.perm_set == researcher.perm_set, "the copy has the same permissions")
    viewer_role = s.scalar(select(Role).where(Role.name == "Viewer"))
    adm_role = s.scalar(select(Role).where(Role.locked))
    s.add(User(username="seller1", password_hash=s.get(User, admin_id).password_hash, role="Buyers team",
               role_id=sales.id, perms="view", all_groups=True, active=True, prefs={}))
    s.commit()
check(c.post("/settings/roles/new", data={"name": "buyers TEAM"}).text.count("unique name") == 1, "role names are unique")
r = c.get("/settings/roles")
check("Delete a role" in r.text and "Give its users this role" in r.text and "A copy of Researcher" in r.text,
      "roles page: new (copy) and delete with move")
r = c.post(f"/settings/roles/{sales.id}/delete", data={})
check("Choose which role they get instead" in r.text, "a role with users needs a replacement role")
r = c.post(f"/settings/roles/{sales.id}/delete", data={"move_to": str(viewer_role.id)})
check("deleted" in r.text and "now have the role Viewer" in r.text, "role deleted, its users moved")
with SessionLocal() as s:
    u = s.scalar(select(User).where(User.username == "seller1"))
    check(u.role_id == viewer_role.id and u.role == "Viewer", "user got the new role")
    check(s.get(Role, sales.id) is None, "role is gone")
r = c.post(f"/settings/roles/{adm_role.id}/delete", data={"move_to": str(viewer_role.id)})
with SessionLocal() as s:
    check(s.get(Role, adm_role.id) is not None and "can't be deleted" in r.text, "Admin role can't be deleted")

# ---------- my password ----------
r = c.get("/account/password")
check(r.status_code == 200 and "Current password" in r.text, "My password page")
r = c.post("/account/password", data={"old": "nope", "new": "abcdefgh1", "new2": "abcdefgh1"})
check("not right" in r.text, "wrong current password refused")

# ---------- pages & log ----------
for url in ["/", "/directories", "/directories?view=list", f"/d/{man.id}", f"/d/{buy.id}?view=list", "/contacts",
            "/contacts?view=list", "/inbox", "/requests", "/settings/users", "/settings/users/new", "/settings/roles",
            "/settings/logins", "/account/password", "/settings/ai", "/help", "/help/dashboard", "/help/people",
            "/help/move-contacts", "/help/whats-new", "/dev"]:
    rr = c.get(url)
    check(rr.status_code == 200 and "Something went wrong" not in rr.text, f"GET {url}")
from app.db import AppLog
with SessionLocal() as s:
    errs = s.scalars(select(AppLog).where(AppLog.level == "error")).all()
    check(not errs, "no errors in the log" + (": " + errs[0].message if errs else ""))

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
