---
title: Moving contacts between directories
section: Using NetGate
order: 35
needs: edit
summary: Move here, Also add here, and moving many at once
---
A contact exists once and can be in several directories. You can move it, or add it to another directory as well.

## One contact
Open the contact's card. Next to its directories, pick a directory and press:
- **Move Here** — it leaves its current directory and goes to the chosen one. If it is in more than one directory, choose **from** which one.
- **Also Add Here** — it stays where it is and is added to the chosen one too.

The × on a directory chip removes it from that directory only (the contact itself is kept).

## Many contacts
Switch to the **List** view, tick the contacts, pick a **Directory** in the bar above the list and press:
- **Move There** — a box asks you to confirm. On a directory's page they leave that directory. On **All Contacts** you choose *From*: all their current directories, or one directory only.
- **Also Add There** — added, nothing removed.

## Before you move: the preview
When you pick the new directory, a short preview shows:
- **Kept but hidden** — details the new directory has no field for (for example *Employees*). Nothing is deleted; they wait under **Other Details** on the big card and come back if a field for them is added.
- **Missing there** — fields of the new directory this contact doesn't have yet.
- **Enrich the missing fields now** — tick it and NetGate starts Enrich for the moved contacts straight away.

## What happens to the details
Everything is kept: fields, notes, links, history. The history gets a line like *Moved from Manufacturers to Buyers & brands by admin*.
If the new directory has fields the old one didn't, they show as **Missing**. **Enrich** fills them as usual (by hand, or at night).

## Other Details and “Same as”
- The big card lists **Other Details** — values the directory you are looking at has no field for. **Add This Field to …** (Manage directories) adds that field to the directory, and the value shows at once.
- In **Directory Settings → Fields**, **Same as** links a field to a field of another directory that means the same thing (for example *Materials* in one directory = *Products* in another). Both then show and fill the same value; values already there are copied across, nothing is deleted. Choose nothing to go back to the field's own data.

You need the permission **Edit contacts** for both directories.
