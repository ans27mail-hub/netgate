---
title: Overview — what NetGate is and how it fits together
order: 10
updated: v0.7
---
NetGate builds and maintains **business directories** for Motofast International (MFI), Sialkot: manufacturers, material suppliers, online retailers, buyers and brands, trade shows and so on. A **local AI** (Ollama on the owner's iMac) reads web pages; **plain code** picks out what it can find reliably; **people decide** what goes into a directory.

## The main flow
```
 keyword / "Run Discovery"                         night run (scheduler)
            │                                              │
            ▼                                              ▼
   ┌──────────────────┐   pages    ┌──────────────┐   text   ┌────────────┐
   │ search methods   │──────────▶ │ crawler +    │────────▶ │ AI + code  │
   │ web · directory  │            │ renderer     │          │ extraction │
   │ site · eBay API  │            └──────────────┘          └─────┬──────┘
   └──────────────────┘                                            │ companies
                                                                   ▼
                                  match existing contact (eBay id → website → name+city)
                                         │ new: create, first finder = who searched
                                         │ existing: fill only empty fields (+ Existing Contacts)
                                         ▼
                                    ┌─────────┐  accept   ┌─────────────┐  Enrich  ┌──────────────┐
                                    │  Inbox  │─────────▶ │  directory  │────────▶ │ more details │
                                    └─────────┘  reject   └─────────────┘          └──────────────┘
                                         │ (reason; never suggested again there)
                                         ▼
                              decisions → AI suggestions (learning) → training export
```

## Words used in the code
| In the UI | In the code / database |
|---|---|
| Directory | `Group` / table `groups` |
| Contact | `Record` / `records` |
| Contact in a directory | `Membership` / `memberships` |
| Inbox item | `InboxItem` / `inbox` |
| Request | `Job` / `jobs` (kind `request`, `keyword`, `enrich`, `night`) |
| Search method | key in `groups.methods` (`web`, `directory`, `ebay`, `website`) |
| First finder | `records.found_by` |

## Main ideas (see `docs/DECISIONS.md`)
- **Nothing reaches a directory without a person accepting it.**
- **One contact, many directories**; matched across all directories.
- **Requests are a separate layer**: deleting or rejecting a request never changes contacts.
- **Code first, AI second.** The AI is only asked for what code can't find.
- **Methods and recipes are code** (GitHub), never edited in the web page.
- **Keep data on upgrades**: every database change is an idempotent upgrade.

## Where to start reading code
`app/main.py` → `app/web/*_routes.py` (pages) → `app/jobs.py` (searching and enriching) → `app/contacts.py` (matching, Inbox, decisions) → `app/db.py` (tables and upgrades). See [Code map](/dev/handbook/code-map).
