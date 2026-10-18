---
title: Directory settings
section: Directories & searching
order: 20
needs: manage_dirs
summary: Methods, fields and “Filled from”, instructions, keywords, page tester
---
Settings → a directory. Sections:

## Basics & Search Methods
Name, description, menu order, words added to every web search, **Owner** (people set to “only their own directories” see the directories they own), and the [search methods](/help/search-methods) with their options.

## Cards
How the short cards look in this directory (empty = the default from Settings → Display):
- **Style A** — tag bars under the Enrich button on the right; **B** — the same on the left; **C** — tags and Enrich on the name line (shortest cards).
- **Card width** — the smallest a card may be (Small 220, Medium 260, Large 320 px or your own).
- **Fill the row** — *On* (the default): cards are never narrower than the width and stretch evenly to fill the whole row, like the directory cards. *Off*: cards keep exactly the width. *Default* follows Settings → Display.
- **Card colour from tags** — on, off (only the small marks), or default.

Which fields a short card shows (up to 3) is the “Card” tick in Fields below, or a contact's big card → **Short Card Shows…**

## Fields & where they come from
| Column | Meaning |
|---|---|
| Type | Text, List, Choice, Number, Email, Website, Phone |
| **Filled from** | *AI + code* (default: from pages read), *Company website only*, *Manual only* (never searched), or a method such as *eBay: positive feedback %* |
| Step | *Find* (filled when the company is found) or *Enrich* (filled later) |
| Search words | Words Enrich adds when searching for this field |
| Choices | The allowed answers for a Choice field |
| Filter / Sort / Card / List | Where the field is used on the directory page |

Removing a field keeps the values already found on the contacts.

## Instructions for the AI
- **What belongs here** — used when judging search results.
- **How to fill the fields** — used by Enrich.
- **Ignore** — pages and companies to skip.

Write them like you would explain it to a new colleague. Short and concrete works best.

## Keywords
Each keyword has **Search with** (all methods, or one) and **Night Jobs** on / off. Keywords on the reject list can't be added.

## Test the instructions on a page
Paste a list page or a company page and press **Test**. You see exactly what Discover would find there — names, what code found (email, phone, social), and whether a next page was found. Nothing is saved.

## Delete directory
A directory can only be deleted when it is **empty**. The Delete button stays switched off while:
- it **still has contacts** — move them to another directory or remove them first (the link opens the list, where you can tick them and use **Move there**);
- **companies are waiting in the Inbox** for it — accept or reject them first (the link opens the Inbox filtered to this directory). Companies you accept join the directory, so they then need to be moved or removed too.

When both are 0, **Delete** removes the directory with its keywords, fields and settings.
