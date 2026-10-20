---
title: Testing Guide
section: Settings
order: 90
summary: Step-by-step checklists to test every feature, saved test runs, a health check and a Test Directory
---
**Menu → Testing Guide** is for admins and anyone given the permission **Testing Guide**.

## Test runs
1. **Start Test Run** — choose **Only what is new** in this version, or **Everything**.
2. Each feature has a checklist. Every step says **what to do** and **what you should see**.
3. Mark each step **Passed**, **Failed** or **Skipped**. It saves at once. Add a **note** (what went wrong) and a **Screenshot** when it helps.
4. **Failed** shows only the failed steps; **Not Done** what is left.
5. The **Report** box lists the failed steps with your notes — **Copy Report** and paste it into your message to the developer.
6. **Finish Run.** Runs are kept per version, so you can compare versions.

Every new version of NetGate adds checklist steps for what it changes (marked **new**).

## Quick Health Check
Checks the database, the queue, NetGate's browser, the search engine, the AI servers, stuck requests, recent errors and the last night run. It **only reads** — nothing is changed — so it is safe any time.

## Test Directory
**Make the Test Directory** creates a hidden directory to try searches, moves and edits without touching real data. Only people with the Testing Guide permission see it; its contacts do not appear in All Contacts or the Inbox for anyone else. **Empty Test Directory** deletes its contacts, Inbox items and requests in one go (a contact that is also in a real directory is kept there).
