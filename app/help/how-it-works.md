---
title: How searching and reading works
section: Directories & searching
order: 40
summary: The crawler, the browser, code-first details and the AI
---
## Reading pages
- Pages are downloaded politely: NetGate follows each site's **robots.txt**, waits between requests to the same site (2 seconds by default) and retries once.
- Pages that need **JavaScript** are opened in a hidden Chromium browser (the *renderer*). In *auto* mode this only happens when a page looks empty.
- Downloaded pages are kept in a **cache** for a few days, so repeated searches are fast.
- **Long pages** are split into parts so nothing at the end is cut off.

## Lists, next pages and profiles
On a list page NetGate follows **Next** links (up to a limit) and, on directory sites, opens each company's **profile** to find its real website, email and phone.

## Code first, then the AI
Plain code reads what is certain: emails (also hidden ones), phone numbers, WhatsApp links, Facebook / Instagram / LinkedIn links and the company data some sites hide for search engines (*schema.org*). The AI is only asked for what code couldn't find — names, cities, products, number of employees and so on — and only from the text of the page. It is told never to guess.

## The AI
The AI runs on your own server (Ollama on the iMac, or another server chosen in Settings → AI servers). Each directory's **instructions** are sent with every question, so better instructions give better results.

## Why results can be wrong
- The page lists a company in a confusing way, or mixes adverts with listings.
- The instructions are too vague (“companies” instead of “factories that make gloves themselves”).
- The keyword is too broad.

Fix it by improving the directory's instructions, testing them on a page, rejecting with reasons (which improves the suggestions) and rejecting bad keywords.
