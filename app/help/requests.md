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
| **Stop** | Ends the request now. Everything already found stays. It can't be resumed, but **Run again** starts it fresh. |
| **Delete** | Moves the request to the **Deleted** tab for 30 days (restore it there), then it is removed. |
| **Reject** | Stops it if needed and puts its keyword on the **reject list** with a reason. That keyword is not searched again — by people, keyword clicks or night jobs — until restored. |
| **Restore** | On a rejected request: takes its keyword off the reject list. |
| **Run again** | Starts a new request with the same search. |

**Pause all** pauses every waiting and running request you may control (admins and managers: everyone's, including the night run). **Resume all** brings them back.

## Contacts are never touched
Requests are a separate layer. Deleting or rejecting a request **never** changes the contacts it found: their data, sources and Inbox items stay. Each contact keeps a history note of how it was found. Contacts are only removed in the Inbox or on a contact's card, on purpose.

## The reject list
The match ignores capitals, word order and plurals: rejecting “leather glove makers” also blocks “Glove Maker Leather”. Similar keywords (most words the same) get a warning but still run. Admins manage the list in Settings → Reject list.

## Who can control what
With *Control own requests* you control your own; with *Control everyone's requests* you control all, including the night run.
