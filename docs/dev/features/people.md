---
title: People — users, roles, logins, passwords
order: 90
updated: v0.9
---
**What it does:** **People** (sidebar) has Users, Roles & Permissions and Login History. Everyone has Settings → My Password.

## How it works
- Permissions = role + person's extras − removals (`users.extra_perms` / `removed_perms`); `auth.can()`; Admin role is locked (everything).
- Users: add (with “must choose own password”), edit role / access / exceptions, switch off (Active), **Reset Password** (logs them out everywhere: the session stores a tag of the password hash), **Delete** (type the name; their work stays as “(deleted user)”). Safety: not yourself, always one active admin.
- Roles: new / copy / rename / delete with “give its users this role”; defaults for new users (directory access, contacts scope, existing-contacts view).
- Login History (`logins`): every attempt with result, browser / system and address; kept 180 days.
- `must_change` → every page redirects to `/account/password` until changed.

## v0.9 — a permission for every page, Cards Only
- New keys `see_dashboard`, `see_inbox`, `see_requests` (`auth.PERM_GROUPS`). Gated: Dashboard (`/` redirects to `/directories` without it; `/dashboard/system`), Inbox page + sidebar link + “waiting in Inbox” numbers + Inbox sort + big-card “In Inbox” badge, Requests page + `/activity` + `/dashboard/jobs` + sidebar link + top-bar AI-jobs pill + night banner. `common.searcher(user)` (any of request / keywords / see_requests / see_inbox) hides keywords, last search and the Existing Contacts tab.
- `_upgrade_v09`: every non-admin role with `view` gets the three keys (and users with `view` as an extra); the keys are removed from `removed_perms` (they didn't exist before); a role **Cards Only** (`view`) is added.

## Files
`app/web/people_routes.py`, `app/web/auth_routes.py`, `app/auth.py`, templates `users.html`, `user_edit.html`, `roles.html`, `logins.html`, `my_password.html`.
