---
title: Backups
section: Settings
order: 50
needs: backups
summary: Automatic nightly backups, Back Up Now, download, restore
---
Settings → **Backups** (needs *Backups*; Admin has it).
- **Back up every night** at a time you choose, and **keep for** N days (older ones are deleted).
- **Back Up Now** makes one within a minute. **Saved Backups** lists them with a **Download** button.
- The **Dashboard** warns under *Needs Attention* when there is no backup yet, backups are switched off, or the last one is more than 2 days old.

## Where backups are kept
In the folder set as `BACKUP_DIR` in the `.env` file of NetGate on the server (normally `~/apps/netgate/backups`). Better: another disk or a shared folder, e.g. `BACKUP_DIR=/mnt/d/netgate-backups`, then run `netgate update`.

## Putting a backup back (restore)
Only on the server, in WSL:
1. `netgate restore` — lists the backups.
2. `netgate restore netgate-20261017-0230.dump` — type **RESTORE** to confirm. NetGate first saves a safety copy of the data as it is now, then replaces all data with the backup and starts again.

`netgate backup` makes a backup from the command line.
