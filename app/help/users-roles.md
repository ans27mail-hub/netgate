---
title: Users and roles
section: Settings
order: 40
needs: manage_users, manage_roles
summary: Who can see and do what
---
## Roles
Settings → **Roles & permissions** shows a grid: roles across the top, permissions down the side. Tick what each role may do. **Changing a role changes everyone who has it.**

| Role | For | Typical permissions |
|---|---|---|
| **Admin** | You | Everything (can't be changed) |
| **Manager** | Runs the work | Directories, keywords, instructions, night jobs, everyone's searches |
| **Researcher** | Uses the site | Run keywords, enrich, review the Inbox, add and edit contacts, control own searches |
| **Viewer** | Looks only | View, filter, export |
| **Developer** | Helps build NetGate | Debug view, logs, page tester, training data, developer help — no users and no API keys |

Add a role with **+ Add role** (start from an existing one). A role can only be deleted when nobody has it. Each role also has a **default directory access** for new users.

## Users
Settings → **Users**:
- **Role** — the person's role.
- **Directory access** — all directories, or only the ticked ones. They then only see those directories and their Inbox items.
- **Give this person their own permissions** — tick to add or remove permissions for just this person. They get a **custom** badge so you can spot them.
- **Active** — untick to block someone without deleting them.

There must always be at least one active admin.
