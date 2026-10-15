"""Passwords, roles and permission checks."""
import base64
import hashlib
import hmac
import os

# (key, label, description)
PERMS = [
    ("view", "View directory", "See listings in their groups"),
    ("request", "Send requests", "Ask the AI to search and crawl the web"),
    ("keywords", "Run keyword updates", "Click keywords and \"Update all keywords\""),
    ("edit", "Edit listings & pictures", "Change fields, upload or replace pictures"),
    ("delete", "Delete listings", "Remove listings permanently"),
    ("manage_groups", "Manage groups & keywords", "Create groups, edit keywords, fields and sorting"),
    ("manage_users", "Manage users", "Add users and change permissions"),
]
PERM_KEYS = [p[0] for p in PERMS]
GLOBAL_PERMS = {"manage_groups", "manage_users"}   # not limited to groups

ROLES = {
    "Admin": PERM_KEYS,
    "Editor": ["view", "request", "keywords", "edit"],
    "Viewer": ["view"],
}


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
    """May this user do `perm` (inside group `group_id`, if given)?"""
    if not user or not user.active:
        return False
    if user.is_admin:
        return True
    if perm not in user.perm_set:
        return False
    if perm in GLOBAL_PERMS or group_id is None or user.all_groups:
        return True
    return group_id in user.group_ids


def sees_all_groups(user) -> bool:
    return bool(user and (user.is_admin or user.all_groups))
