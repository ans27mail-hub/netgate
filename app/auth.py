"""Passwords, permissions and roles.

A user's permissions = their role's permissions + their own extras - their own removals.
Directory permissions (DIR_PERMS) are limited to the directories the user may see; the rest are global.
"""
import base64
import hashlib
import hmac
import os

# (group label, [(key, label, description)])
PERM_GROUPS = [
    ("Contacts", [
        ("view", "View contacts", "See contacts in their directories"),
        ("see_dashboard", "See the Dashboard", "The start page with numbers, things to do and system status (without it the start page is Directories)"),
        ("export", "Export", "Download contacts as CSV"),
        ("edit", "Edit contacts", "Change fields, add a contact to a directory"),
        ("delete", "Delete contacts", "Remove contacts permanently"),
        ("add_contacts", "Add contacts by hand", "One contact, a pasted list or a CSV file"),
    ]),
    ("Searching", [
        ("request", "Run discovery", "Ask the AI to search for new companies"),
        ("keywords", "Run keywords", "Click a directory's keywords and “Run all”"),
        ("enrich", "Enrich", "Look for missing details of a contact"),
        ("enrich_others", "Enrich other people's contacts", "Also contacts someone else found first"),
        ("see_methods", "See search methods", "See and choose a directory's search methods (web, directory site, eBay …)"),
        ("see_requests", "See requests and AI jobs", "The Requests page and the “AI Jobs Running” list in the top bar"),
        ("requests_own", "Control own requests", "Pause, stop, delete or reject their own requests"),
        ("requests_all", "Control everyone's requests", "Includes the night run and “Pause all”"),
        ("reject_list", "Manage the reject list", "Restore rejected keywords"),
    ]),
    ("Inbox", [
        ("see_inbox", "See the Inbox", "Open the Inbox of new companies (needed for reviewing too)"),
        ("review", "Review the Inbox", "Accept or reject new companies"),
    ]),
    ("Directories", [
        ("manage_dirs", "Manage directories", "Create directories; edit search methods, fields, keywords and AI instructions"),
        ("manage_tags", "Manage tags", "Create, colour, order, merge and delete tags (anyone who may edit contacts can put tags on them)"),
    ]),
    ("System", [
        ("ai", "AI servers & models", "Choose which AI server and model each job uses"),
        ("crawler", "Crawler settings", "Browser, next pages, cache, polite limits"),
        ("night", "Night jobs", "When and what runs at night"),
        ("display_all", "Display & themes for everyone", "Page width, cards, default view and the theme for all users"),
        ("backups", "Backups", "Automatic database backups, Back Up Now, download backups"),
        ("connections", "Connections (API keys)", "eBay and Etsy keys"),
    ]),
    ("People", [
        ("manage_users", "Manage users", "Add users, choose their role and directories"),
        ("manage_roles", "Manage roles", "Create roles and change what each role may do"),
    ]),
    ("Developer tools", [
        ("debug", "Debug view", "For each request: pages read, what code found, what the AI was asked and answered"),
        ("logs", "Logs", "NetGate's own error and event log"),
        ("tester", "Page tester", "Try a page with a directory's instructions without saving anything"),
        ("training_export", "Training-data export", "Download accept / reject decisions for fine-tuning"),
        ("dev_help", "Developer help", "Technical guides: how NetGate is built and released"),
    ]),
]
PERMS = [p for _, items in PERM_GROUPS for p in items]
PERM_KEYS = [p[0] for p in PERMS]
PERM_LABELS = {k: label for k, label, _ in PERMS}
DIR_PERMS = {"view", "export", "edit", "delete", "add_contacts", "request", "keywords", "enrich", "enrich_others",
             "review"}
ALIASES = {"manage_groups": "manage_dirs"}   # names used before v0.5

ADMIN = "Admin"
DEFAULT_ROLES = [
    # (name, description, perms)
    (ADMIN, "Everything. This role can't be changed or locked out.", PERM_KEYS),
    ("Manager", "Runs the work: directories, keywords, instructions, night jobs and everyone's searches.",
     ["view", "see_dashboard", "see_inbox", "see_requests", "export", "edit", "delete", "add_contacts", "request", "keywords", "enrich", "enrich_others",
      "see_methods", "requests_own", "requests_all", "reject_list", "review", "manage_dirs", "manage_tags", "ai",
      "crawler", "night", "display_all", "tester", "debug"]),
    ("Researcher", "Uses the site: runs keywords, enriches, reviews the Inbox and adds contacts.",
     ["view", "see_dashboard", "see_inbox", "see_requests", "export", "edit", "add_contacts", "request", "keywords",
      "enrich", "enrich_others", "requests_own", "review"]),
    ("Viewer", "Looks only: views and filters contacts, can export.",
     ["view", "see_dashboard", "see_inbox", "see_requests", "export"]),
    ("Developer", "Helps build NetGate: testing and debugging tools, no users and no API keys.",
     ["view", "see_dashboard", "see_inbox", "see_requests", "export", "request", "keywords", "enrich", "see_methods",
      "requests_own", "debug", "logs", "tester",
      "training_export", "dev_help"]),
]

# v0.4 permission keys -> v0.5 keys (used once, when upgrading users)
OLD_PERMS = {
    "view": ["view", "export"],
    "request": ["request", "enrich", "add_contacts", "requests_own"],
    "keywords": ["keywords"],
    "edit": ["edit", "review"],
    "delete": ["delete"],
    "manage_groups": ["manage_dirs", "ai", "crawler", "night", "display_all", "connections", "tester",
                      "reject_list", "requests_all", "debug"],
    "manage_users": ["manage_users", "manage_roles"],
}


def split(text: str | None) -> set[str]:
    return {p.strip() for p in (text or "").split(",") if p.strip()}


def join(perms) -> str:
    return ",".join(k for k in PERM_KEYS if k in set(perms))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
    except ValueError:
        return False
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(dk, expected)


def can(user, perm: str, group_id: int | None = None) -> bool:
    """May this user do `perm` (inside directory `group_id`, if given)?"""
    if not user or not user.active:
        return False
    if user.is_admin:
        return True
    perm = ALIASES.get(perm, perm)
    if perm not in user.perm_set:
        return False
    if perm not in DIR_PERMS or group_id is None or user.all_groups:
        return True
    return group_id in user.group_ids


def can_any(user, perms) -> bool:
    return any(can(user, p) for p in perms)


def sees_all_groups(user) -> bool:
    return bool(user and (user.is_admin or user.all_groups))


def own_contacts_only(user) -> bool:
    """This person only sees the contacts they found first (or added)."""
    return bool(user and not user.is_admin and (user.contacts_scope or "all") == "own")


def sees_methods(user) -> bool:
    return can(user, "see_methods") or can(user, "manage_dirs")


def best_role(target: set[str], roles: list) -> tuple:
    """Pick the role closest to a set of permissions. Returns (role, extra, removed)."""
    best, best_score = None, -1.0
    for r in roles:
        if r.locked:
            continue
        rp = split(r.perms)
        union = target | rp
        score = len(target & rp) / len(union) if union else 1.0
        if score > best_score:
            best, best_score = r, score
    if not best:
        return None, target, set()
    rp = split(best.perms)
    return best, target - rp, rp - target
