---
title: People — users, roles and logins
section: Settings
order: 40
needs: manage_users, manage_roles
summary: Add, change, switch off or delete users; roles; login history; passwords
---
Open **People** in the menu on the left. It has three tabs: **Users**, **Roles & Permissions** and **Login History**.

## Users
The list shows everyone with their role, directories, status and **Last Login**. Search by name, or filter by role or status.

**+ Add User** — username, a first password and a role. Leave *Ask them to choose their own password* ticked: when they first log in, NetGate asks them for a new password before anything else.

On a user's page:
- **Role** — what they may do (see below).
- **Directory access** — all directories, or only the ticked ones. They then only see those directories and their Inbox items.
- **What This Person Sees:**
  - *Directories*: all, only selected ones, or only **their own** (directories they created or that have them as **Owner** in Directory Settings).
  - *Contacts*: all, or only **their own** — the ones they found first (their searches) or added by hand.
  - *Existing Contacts their searches find*: the **full card** or **only chosen fields**. These show in the directory's Existing Contacts tab.
- **Give this person their own permissions** — add or remove permissions for just this person. They get a **custom** badge. Two permissions matter here: **See search methods** (without it, method names and choices are hidden; their searches still use all methods) and **Enrich other people's contacts**.
- **Active** — untick to switch the account off without deleting it. They can't log in and are told the account is switched off.
- **Reset Password** — type a new password for them and tell them yourself. They are logged out on every computer and, if ticked, must choose their own at their next login.
- **Recent Logins** — when and from which computer (browser and system).
- **Delete User** — type the username to confirm. The account is removed, but everything they found, added, accepted or rejected stays in NetGate and shows as **(deleted user)**. Their requests stay too.

Safety rules: you can't delete or switch off your own account, and there is always at least one active admin.

## Roles & permissions
A grid: roles across the top, permissions down the side. Tick what each role may do and press **Save Roles**. **Changing a role changes everyone who has it.**

| Role | For | Typical permissions |
|---|---|---|
| **Admin** | You | Everything (can't be changed or deleted) |
| **Manager** | Runs the work | Directories, keywords, instructions, night jobs, everyone's searches |
| **Researcher** | Uses the site | Run keywords, enrich, review the Inbox, add contacts, control own searches |
| **Viewer** | Looks only | View, filter, export |
| **Cards Only** | Only looks at the cards | View contacts — nothing else: no Dashboard, Inbox, requests, searching or export |
| **Developer** | Helps build NetGate | Debug view, logs, page tester, training data, developer help — no users and no API keys |

Every page and button has its own permission, and is hidden when the person doesn't have it. Some useful ones:
- **See the Dashboard** — without it, the start page is **Directories**.
- **See the Inbox** — the Inbox page and the “waiting in the Inbox” numbers.
- **See requests and AI jobs** — the Requests page and the “AI Jobs Running” list at the top.
- **Run discovery**, **Run keywords**, **Enrich**, **Add contacts by hand**, **Export** — each one separately.

So a person who should **only see the cards** gets the **Cards Only** role (or any role with only *View contacts* ticked). They see the directories and the contact cards, and nothing about searching.

- **Rename** a role: type the new name at the top of its column, then **Save Roles**.
- **New Role**: give it a name and start from nothing or from **a copy of** an existing role, then change the ticks.
- **Delete a Role**: pick it and, if people have it, the role they get instead. Nobody is left without a role.
- Each role has a **default directory access** for new users.

## Login history
Every login and every failed attempt: who, when, the computer (e.g. *Chrome on Windows*) and its network address. Filter by person or *Failed attempts only*. Many failed attempts for one name can mean someone is guessing a password. Kept 180 days, also for deleted users.

## My password
Everyone can change their own password under **Settings → My password**. Other computers where you are logged in are logged out.
