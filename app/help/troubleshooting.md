---
title: Troubleshooting
section: Troubleshooting
order: 10
summary: No results, AI not reachable, browser not running …
---
## A search finds nothing or very little
- Open the request's **Debug** view (Requests → Debug, for people with the Debug permission): see which pages were read and what the AI answered.
- Make the keyword more specific, and check the directory's *What belongs here* instruction isn't too strict.
- Test a good list page in Directory settings → **Test the Instructions on a Page**.
- A search engine may be blocking: **Settings → Search Engines** shows which engines work and which block, and since when. Switch a blocking one off, or press **Test Each Engine**.
- On the Requests page, use **Edit** to change the words, or **Go Deeper** to read more result pages, inside the same request.

## “AI not reachable” / AI errors
- Is the iMac on and awake? Is Ollama running?
- Settings → AI servers → press **Test** on the server.
- The model name for the job must exist on that server.

## The browser is “not reachable”
Settings → Crawler shows the browser status. In WSL run:
`cd ~/apps/netgate && docker compose logs --tail 30 renderer`
and send the last lines to whoever maintains NetGate.

## Wrong companies in a directory
- Reject them with a reason — the suggestions learn from it.
- Improve *What belongs here* and *Ignore* in Directory settings.
- Reject the request of a keyword that keeps giving wrong results.

## eBay search was skipped
The request says so when the keys are missing or wrong: add or check them in Settings → Connections and press **Save & Test eBay Keys**.

## A request stays “pausing” or “stopping”
It finishes the page it is reading first (a big page can take a minute). If the worker was restarted in the middle, press **Stop**, then **Run Again**.

## After an update something is wrong
In WSL: `netgate rollback` goes back to the previous version; `netgate versions` lists them.
