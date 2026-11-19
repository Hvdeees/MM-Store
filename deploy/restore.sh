#!/bin/bash
# Restore a backup.
#   bash deploy/restore.sh --check /opt/mmstore-backups/db_2026-11-20_0300.dump   # test it, live data untouched
#   bash deploy/restore.sh /opt/mmstore-backups/db_2026-11-20_0300.dump           # REPLACE live data with it
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
CHECK=false
[ "${1:-}" = "--check" ] && { CHECK=true; shift; }
FILE="${1:?usage: restore.sh [--check] fichier.dump}"
[ -f "$FILE" ] || { echo "Fichier introuvable : $FILE"; exit 1; }

if $CHECK; then
  # Restore into a throw-away database and count what's inside: proves the backup can really be restored.
  $COMPOSE exec -T db dropdb -U boutique --if-exists restore_check
  $COMPOSE exec -T db createdb -U boutique restore_check
  $COMPOSE exec -T db pg_restore -U boutique --no-owner -d restore_check < "$FILE"
  $COMPOSE exec -T db psql -U boutique -d restore_check -At -c \
    "select 'produits: ' || count(*) from products union all select 'ventes: ' || count(*) from sales union all select 'revendeurs: ' || count(*) from resellers"
  $COMPOSE exec -T db dropdb -U boutique restore_check
  echo "✅ Sauvegarde lisible et complète. Les données en service n'ont pas été touchées."
  exit 0
fi

echo "⚠️  Ceci REMPLACE toutes les données actuelles par celles de : $FILE"
read -rp "Tapez RESTAURER pour continuer : " ANSWER
[ "$ANSWER" = "RESTAURER" ] || { echo "Annulé."; exit 1; }
deploy/backup.sh                       # safety copy of the current state first
$COMPOSE stop api
$COMPOSE exec -T db pg_restore -U boutique --clean --if-exists --no-owner -d boutique < "$FILE"
$COMPOSE start api
echo "✅ Données restaurées. (Les photos se restaurent à part : media_*.tar.gz)"
