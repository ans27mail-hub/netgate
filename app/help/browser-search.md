---
title: Browser Search and Solve CAPTCHA Yourself
section: Directories & searching
order: 29
summary: Search Bing, DuckDuckGo or Google in NetGate's own browser, and answer a CAPTCHA yourself when one appears
---
**Browser Search** is a search method: NetGate opens the search engine in its own hidden browser, the way a person would, reads the result links, and then reads those pages like Web search. It helps when the normal search (SearXNG) is blocked or finds too little.

## Turn it on
**Directory Settings → Search Methods → Browser Search.** Options: how many companies to find, how many result pages per search, the most minutes per search, and which engines.

**Settings → Search Engines → Browser Search** (for everyone): which engines it may use, the pause between searches, the most searches per hour per engine, how long to wait for a person when a CAPTCHA appears, and how many hours to rest an engine after a CAPTCHA nobody solved.

## When a CAPTCHA appears
Search engines sometimes ask “are you a robot?”. **NetGate never solves these itself.**
- The search **waits a few minutes** for a person.
- The person who started the request gets a **pop-up “Solve the CAPTCHA”** on whatever page they have open. The **Dashboard → Needs Attention** also shows it, with a **Solve** button (for people who may control that request).
- The pop-up shows a **live picture of the page**. Click on it and type into the box under it exactly as you would on the real page. When the page is answered, the pop-up says so and closes, and the search goes on.
- **Give Up** (or nobody answering in time) **rests that engine** for some hours. Settings → Search Engines shows it as paused, with **Use Again Now**.
