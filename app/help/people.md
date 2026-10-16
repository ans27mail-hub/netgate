---
title: People — users, roles and logins
section: Settings
order: 40
needs: manage_users, manage_roles
summary: Add, change, switch off or delete users; roles; login history; passwords
---
Open **People** in the menu on the left. It has three tabs: **Users**, **Roles & permissions** and **Login history**.

## Users
The list shows everyone with their role, directories, status and **last login**. Search by name, or filter by role or status.

**+ Add user** — username, a first password and a role. Leave *Ask them to choose their own password* ticked: when they first log in, NetGate asks them for a new password before anything else.

On a user's page:
- **Role** — what they may do (see below).
- **Directory access** — all directories, or only the ticked ones. They then only see those directories and their Inbox items.
- **Give this person their own permissions** — add or remove permissions for just this person. They get a **custom** badge.
- **Active** — untick to switch the account off without deleting it. They can't log in and are told the account is switched off.
- **Reset password** — type a new password for them and tell them yourself. They are logged out on every computer and, if ticked, must choose their own at their next login.
- **Recent logins** — when and from which computer (browser and system).
- **Delete user** — type the username to confirm. The account is removed, but everything they found, added, accepted or rejected stays in NetGate and shows as **(deleted user)**. Their requests stay too.

Safety rules: you can't delete or switch off your own account, and there is always at least one active admin.

## Roles & permissions
A grid: roles across the top, permissions down the side. Tick what each role may do and press **Save roles**. **Changing a role changes everyone who has it.**

| Role | For | Typical permissions |
|---|---|---|
| **Admin** | You | Everything (can't be changed or deleted) |
| **Manager** | Runs the work | Directories, keywords, instructions, night jobs, everyone's searches |
| **Researcher** | Uses the site | Run keywords, enrich, review the Inbox, add contacts, control own searches |
| **Viewer** | Looks only | View, filter, export |
| **Developer** | Helps build NetGate | Debug view, logs, page tester, training data, developer help — no users and no API keys |

- **Rename** a role: type the new name at the top of its column, then **Save roles**.
- **New role**: give it a name and start from nothing or from **a copy of** an existing role, then change the ticks.
- **Delete a role**: pick it and, if people have it, the role they get instead. Nobody is left without a role.
- Each role has a **default directory access** for new users.

## Login history
Every login and every failed attempt: who, when, the computer (e.g. *Chrome on Windows*) and its network address. Filter by person or *Failed attempts only*. Many failed attempts for one name can mean someone is guessing a password. Kept 180 days, also for deleted users.

## My password
Everyone can change their own password under **Settings → My password**. Other computers where you are logged in are logged out.
