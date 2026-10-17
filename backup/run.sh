#!/bin/sh
# NetGate backups. Runs in the `backup` container (postgres:16 image, so pg_dump matches the database).
# Every minute: read the settings NetGate saved, make a backup when it's time or when "Back Up Now" was pressed,
# delete backups older than "keep days", and write the result back for the Settings → Backups page.
# Needs: PGHOST PGUSER PGPASSWORD PGDATABASE, BACKUP_DIR (default /backups). TZ sets the local time.
set -u
DIR="${BACKUP_DIR:-/backups}"
mkdir -p "$DIR"

q() { psql -X -q -t -A -c "$1" 2>/dev/null; }

setting() {   # setting <key> <json field> <default>
  v=$(q "SELECT COALESCE(value::jsonb ->> '$2', '') FROM app_settings WHERE key = '$1'")
  [ -n "$v" ] && echo "$v" || echo "$3"
}

save_status() {   # save_status <ok:1|0> <file> <size> <error>
  now=$(date -u +%Y-%m-%dT%H:%M:%S)
  old_ok=$(setting backups.status last_ok_at "")
  old_file=$(setting backups.status last_file "")
  old_size=$(setting backups.status last_size "0")
  if [ "$1" = "1" ]; then ok_at="$now"; file="$2"; size="$3"; err=""; else ok_at="$old_ok"; file="$old_file"; size="$old_size"; err="$4"; fi
  err=$(printf '%s' "$err" | tr -d "'\"\\\\" | tr '\n' ' ' | cut -c1-300)
  json="{\"last_try_at\": \"$now\", \"last_ok_at\": \"$ok_at\", \"last_file\": \"$file\", \"last_size\": ${size:-0}, \"last_error\": \"$err\"}"
  q "INSERT INTO app_settings (key, value) VALUES ('backups.status', '$json') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value" >/dev/null
}

backup_now() {
  name="netgate-$(date +%Y%m%d-%H%M).dump"
  if out=$(pg_dump -Fc -f "$DIR/$name.part" 2>&1); then
    mv "$DIR/$name.part" "$DIR/$name"
    size=$(wc -c < "$DIR/$name" | tr -d ' ')
    save_status 1 "$name" "$size" ""
    echo "$(date) backup $name ($size bytes)"
  else
    rm -f "$DIR/$name.part"
    save_status 0 "" 0 "$out"
    echo "$(date) backup FAILED: $out"
  fi
  keep=$(setting backups keep_days 14)
  find "$DIR" -name 'netgate-*.dump' -type f -mtime +"$keep" -exec rm -f {} \;
}

echo "NetGate backup service: folder $DIR"
last_day=""
while true; do
  if q "SELECT 1" >/dev/null; then
    enabled=$(setting backups enabled true)
    at=$(setting backups time 02:30)
    asked=$(q "SELECT CASE WHEN COALESCE((SELECT value::jsonb ->> 'at' FROM app_settings WHERE key = 'backups.request'), '') > COALESCE((SELECT value::jsonb ->> 'last_try_at' FROM app_settings WHERE key = 'backups.status'), '') THEN 1 ELSE 0 END")
    today=$(date +%Y%m%d)
    now_hm=$(date +%H%M)
    want_hm=$(echo "$at" | tr -d ':')
    done_today=$(ls "$DIR"/netgate-"$today"-*.dump 2>/dev/null | head -1)
    if [ "$asked" = "1" ]; then
      backup_now
    elif [ "$enabled" = "true" ] && [ "$now_hm" -ge "$want_hm" ] && [ -z "$done_today" ] && [ "$last_day" != "$today" ]; then
      last_day="$today"
      backup_now
    fi
  fi
  [ "${RUN_ONCE:-}" = "1" ] && exit 0
  sleep 60
done
