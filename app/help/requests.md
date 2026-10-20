---
title: Requests: pause, stop, delete, reject
section: Using NetGate
order: 60
summary: Control every search and enrich
---
Every search and enrich is a **request**. The **Requests** page lists them with tabs: All · Running · Waiting · Paused · Done · Failed · Stopped · Rejected · Deleted.

## What each button does
| Button | What happens |
|---|---|
| **Pause** | A running request finishes the page it is reading, saves where it got to and frees the worker. A waiting one simply doesn't start. |
| **Resume** | Continues from where it paused, not from the start. |
| **Stop** | Ends the request now. Everything already found stays. It can't be resumed, but **Run Again** starts it fresh. |
| **Delete** | Moves the request to the **Deleted** tab for 30 days (restore it there), then it is removed. |
| **Reject** | Stops it if needed and puts its keyword on the **Reject List** with a reason. That keyword is not searched again — by people, keyword clicks or night jobs — until restored. |
| **Restore** | On a rejected request: takes its keyword off the reject list. |
| **Edit** | On a finished, failed or stopped search: change it and run it again **inside the same request** (see below). |
| **Run Again** | Starts a **new** request with the same search (and the same methods). |
| **Force Stop** | Admins (*Control everyone's requests*): ends a request stuck in *Pausing* or *Stopping* straight away. |

**Pause All** pauses every waiting and running request you may control (admins and managers: everyone's, including the night run). **Resume All** brings them back.

## Interrupted requests
When NetGate restarts — for example after `netgate update` — a request that was running can't continue. It is marked **Interrupted (NetGate restarted)** and shows in the **Failed** tab with **Run Again**, **Edit** and **Delete**. Requests that were still waiting simply start again by themselves.

A request that makes **no progress for 30 minutes** is marked *Interrupted* the same way, so nothing stays “running” for ever.

## Edit and Run Again
When a search found too little, press **Edit** (or **Edit and Run Again** on its Debug page). You can change:
- **Search for** — different words;
- **Directory** — another directory you may search in;
- **Search methods** — if you may see them;
- **How deep** — *Normal*, or *Deeper* level 1 to 3: more pages of search results and more “next” pages of lists. **Go Deeper and Run** goes one level deeper than the last try.

**Run Again in This Request** runs it again in the same request. The request keeps a list of its **Tries** (the words, directory, depth, how many companies each try found). **Nothing found earlier is removed**: companies from earlier tries stay in the Inbox. A request that was edited shows a small **Try 2**, **Try 3** … badge.

When a search finished and found nothing, the Requests page says **Nothing found — try different words or Go Deeper**.

**Save as Keyword** (in the Tries list) adds a good try's words to the keywords of its directory, so it can be run again with one click and at night. It needs *Run keywords* for that directory (or *Manage directories*).

Your own requests can be edited with *Control own requests*; other people's with *Control everyone's requests*. Pages read by earlier tries are skipped (see [Pages read](/help/pages-read)).

**Pick From the Keyword Library** on the Edit page builds the new search from library words, in any of the directory's languages. Each try shows its language.

## Contacts are never touched
Requests are a separate layer. Deleting or rejecting a request **never** changes the contacts it found: their data, sources and Inbox items stay. Each contact keeps a history note of how it was found. Contacts are only removed in the Inbox or on a contact's card, on purpose.

## The reject list
The match ignores capitals, word order and plurals: rejecting “leather glove makers” also blocks “Glove Maker Leather”. Similar keywords (most words the same) get a warning but still run. Admins manage the list in Settings → Reject list.

## Who can control what
With *Control own requests* you control your own; with *Control everyone's requests* you control all, including the night run.
