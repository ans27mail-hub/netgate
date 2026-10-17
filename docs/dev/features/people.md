---
title: People — users, roles, logins, passwords
order: 90
updated: v0.7
---
**What it does:** **People** (sidebar) has Users, Roles & Permissions and Login History. Everyone has Settings → My Password.

## How it works
- Permissions = role + person's extras − removals (`users.extra_perms` / `removed_perms`); `auth.can()`; Admin role is locked (everything).
- Users: add (with “must choose own password”), edit role / access / exceptions, switch off (Active), **Reset Password** (logs them out everywhere: the session stores a tag of the password hash), **Delete** (type the name; their work stays as “(deleted user)”). Safety: not yourself, always one active admin.
- Roles: new / copy / rename / delete with “give its users this role”; defaults for new users (directory access, contacts scope, existing-contacts view).
- Login History (`logins`): every attempt with result, browser / system and address; kept 180 days.
- `must_change` → every page redirects to `/account/password` until changed.

## Files
`app/web/people_routes.py`, `app/web/auth_routes.py`, `app/auth.py`, templates `users.html`, `user_edit.html`, `roles.html`, `logins.html`, `my_password.html`.
