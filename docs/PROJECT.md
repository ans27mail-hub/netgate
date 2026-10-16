# NetGate — the project

## What it is for
NetGate builds and maintains **business directories** for **Motofast International (MFI)**, an export manufacturer of motorcycle apparel and protective gear in Sialkot, Pakistan. Typical directories:

- **Manufacturers** — factories and workshops (competitors, partners, sub-contractors)
- **Materials** — suppliers of leather, textiles, armour, zips, trims
- **Online retailers** — shops (own web shops, eBay, Etsy, Amazon sellers) that sell motorcycle apparel: possible customers
- **Buyers & brands**, **Trade shows**, **Logistics**, **Standards**

A local AI searches and reads the web, fills each company's details, and people decide what goes in.
The owner wants it to work largely by itself (night jobs), but with people in control (Inbox, accept / reject).

## Who uses it
| Person | What they do |
|---|---|
| **Abdul Moeez** (owner, admin) | Sets up directories, decides direction, runs updates |
| **Researchers** (staff) | Run keywords, review the Inbox, add contacts, enrich |
| **Viewers** (sales, management) | Look up and export contacts |
| **Developer** (maybe later) | Improves NetGate; works through GitHub, uses Developer tools in the app |

The owner is not a programmer. Everything must be explained in plain words and be installable with one command.

## The owner's setup
- **AI server:** iMac M4 (16 GB) running **Ollama** on the office network (`http://192.168.33.17:11434`), model **qwen3:8b** (qwen3.5:9b considered). A PC with a 16 GB GPU (RTX 4090 class) may come later for bigger models and fine-tuning.
- **NetGate server:** the owner's Windows PC, **Docker inside WSL**, code in `~/apps/netgate`, opened at `http://localhost:8090` (and from the office network).
- **Code:** GitHub repository `ans27mail-hub/netgate` (the owner plans to make it private; then the PC needs a read-only token — see `docs/ARCHITECTURE.md` → Updates).
- **Commands in WSL:** `netgate update` (install the newest version), `netgate rollback [v0.x]`, `netgate versions`, `netgate version`.
- Optional: OpenRouter (paid cloud AI) can be added in Settings with spending limits; not used for now.
- Related tools the owner runs: Open WebUI on the PC (chat with the same AI), possibly ComfyUI later (images). Not part of NetGate.

## Goals
1. Find the right companies (quality over quantity) and keep their details complete and current.
2. Let people correct the AI quickly (Inbox, reasons), and use those corrections to get better (suggestions now, fine-tuning later).
3. Marketplace sellers (eBay first, then Etsy / Amazon) as a source of possible customers.
4. Easy to hand over: a new person learns it from the in-app Help; a new developer / AI from `AGENTS.md`.

## Not goals (for now)
- Sending emails or marketing from NetGate.
- Running in the cloud (it runs on the owner's PC; a VPS was discussed as an option later).
- Editing code or scripts from the web page.
