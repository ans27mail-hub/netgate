# Design

## Direction
- **v0.2–v0.4:** layout “D” — dark top bar, directory tabs, compact cards that open into a big card, optional list view.
- **v0.6:** layout **D5** — sidebar: Dashboard, Inbox, All contacts, Directories, Saved views; bottom: Requests, People, Settings, Help, Developer tools. Directory pages get a tab bar (switcher). Mockups D5-Dashboard, D5-Directories, D5-Directory, D5-Move on the design canvas.
- **v0.5:** layout **D4** — a dark **left sidebar** (Inbox with count, All contacts, Directories with counts and a find box, Saved views; at the bottom Requests, Settings, Help, Developer tools, user) and a white top bar (search, AI jobs running, ?, + Add contact, + Run discovery).

The D4 mockups are on the owner's design canvas (claude.ai artifact *NetGate layouts*): artboards D4-Inbox, D4-Contacts, D4-Directory, D4-NewDirectory, D4-AddContact. Screenshots of the built pages are in `docs/design/`.

## Look
- Font: Instrument Sans (UI), JetBrains Mono (addresses, codes).
- Colours: ink `#16181d`, page `#f4f6f9`, cards white with `#e3e6eb` border, accent blue `#2457d6`. Method badges: eBay amber, Etsy rust, web blue, directory green, manual purple.
- Filter chips are black with a ×; “+ Add filter” is a dashed chip.
- Completeness bar: green ≥ 80 %, blue, amber < 50 %.
- Plain-English labels, short hints under fields, no jargon.

## Pages (v0.6 screenshots)
| Page | Screenshot |
|---|---|
| Dashboard | `design/dashboard.png` |
| Directories | `design/directories.png` |
| A directory with the switcher | `design/directory-switcher.png` |
| Users (People) | `design/people-users.png` |

## Pages (v0.5)
| Page | Screenshot |
|---|---|
| Inbox | `design/inbox.png` |
| All contacts (list) | `design/contacts.png` |
| A directory | `design/directory.png` |
| Add contact | `design/add-contact.png` |
| Requests | `design/requests.png` |
| New directory | `design/new-directory.png` |
| Roles & permissions | `design/roles.png` |
| Help | `design/help.png` |
| Inbox on a phone | `design/mobile-inbox.png` |

## Owner's preferences
- Show mockups before building bigger layout changes.
- Display width setting: fixed px, % of the screen (adjustable), or full width.
- Cards: picture top-left (planned), hover popup with the description, click to open the big card.
