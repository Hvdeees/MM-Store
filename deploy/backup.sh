#!/bin/bash
# Daily backup: the database (all sales, stock, resellers…) and the product photos.
# Kept 30 days in /opt/mmstore-backups; also copied to Google Drive if rclone has a "gdrive" remote.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
DEST="${BACKUP_DIR:-/opt/mmstore-backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$DEST" && chmod 700 "$DEST"

# Write to a temporary name first: a half-written file must never look like a good backup.
$COMPOSE exec -T db pg_dump -U boutique --format=custom boutique > "$DEST/db_$STAMP.dump.part"
mv "$DEST/db_$STAMP.dump.part" "$DEST/db_$STAMP.dump"
$COMPOSE exec -T api tar -C /code -czf - media > "$DEST/media_$STAMP.tar.gz.part"
mv "$DEST/media_$STAMP.tar.gz.part" "$DEST/media_$STAMP.tar.gz"

find "$DEST" -name 'db_*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name 'media_*.tar.gz' -mtime +"$KEEP_DAYS" -delete

if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -q '^gdrive:$'; then
  rclone copy "$DEST" gdrive:MM-Store-sauvegardes --max-age 48h
  echo "$(date '+%F %T') copie vers Google Drive : OK"
fi
echo "$(date '+%F %T') sauvegarde OK : db_$STAMP.dump ($(du -h "$DEST/db_$STAMP.dump" | cut -f1))"
