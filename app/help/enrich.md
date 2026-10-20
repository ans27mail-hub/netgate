---
title: Fill missing details (Enrich)
section: Using NetGate
order: 40
needs: enrich
summary: How Enrich finds emails, phones, websites and more
---
**Enrich** looks for a contact's missing fields. Start it with the round-arrow button on a card, **Enrich Now** on an open card, **Enrich Selected** in list view, or **Enrich** in the Inbox.

## The steps
1. **eBay store lookup** — if the contact has an eBay link, reads the seller's details (rating, feedback, business name, address, email, phone).
2. **Find own website** — searches the name with the city / country to find the company's own website.
3. **Company website** — reads the home, Contact, About and Impressum pages and the sitemap. Code finds emails, phones, WhatsApp, social links and addresses; the AI fills the rest.
4. **Social links** — finds Facebook, Instagram and LinkedIn pages.
5. **Other pages** — reads other pages that mention the company, and search-result snippets.

Each step uses what the one before found.

## Choosing the steps: Enrich Now ▾
The small **▾** next to **Enrich Now** (on an open card) and next to **Enrich Selected** (list view) opens a menu:
- tick the **steps** to run this time. A step that can't work is greyed out with the reason (for example *No eBay seller known*, *Its website is already known*);
- **Only Missing Fields** (normal) or **Check All Again** (looks at every field again, and reads pages it read before again);
- **Extra search words** for this time, e.g. *biker jackets*.

Your choice is remembered for next time. People who don't see the search methods just get **Enrich Now**: it uses the directory's own steps.

## How it searches
Enrich builds its searches from what is already known: the name with the city, **your extra words**, the **website address** in quotes, the **search that found the company**, its **products**, the fields still missing, the directory's own **Enrich words** and its **B2B sites**. It stops as soon as every field is filled.

Each directory sets this in **Directory Settings → Enrich**: its own search words, which steps it uses, how many results it reads per search and at most how many searches per contact.

## Pages read before
NetGate keeps a [list of every page it reads](/help/pages-read). Enrich doesn't open a page again that it already read for the same company — it reuses what it found there. **Check All Again** reads everything again. The open card shows **Pages Read**.

## Good to know
- Only empty fields are filled; nothing typed by a person is overwritten.
- Each value shows its source on the card (a web page, *eBay*, *edited by …*).
- Fields set to *Manual only* are never searched.
- Notes on a contact are given to the AI as a hint.
- The request's **Debug** page shows every search with the reason it was made, and **Fields Filled**: which page filled which field.
