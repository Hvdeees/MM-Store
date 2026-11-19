#!/bin/bash
# One-time installation of MM Store on a fresh Ubuntu 24.04 server. Run as root from the project folder:
#   cd /opt/mmstore && bash deploy/setup-server.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "Lancez ce script en root (sudo)."; exit 1; }
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "== 1/6 Logiciels (Docker, pare-feu, mises à jour de sécurité automatiques)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git ufw unattended-upgrades cron curl openssl
systemctl enable --now docker cron

echo "== 2/6 Pare-feu : seuls SSH, HTTP et HTTPS sont ouverts"
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
ufw --force enable >/dev/null

echo "== 3/6 Réglages (.env)"
if [ ! -f .env ]; then
  read -rp "Nom de domaine (ex. caisse.mmstore.ma) : " DOMAIN
  read -rp "Email pour le certificat HTTPS (celui du propriétaire) : " ACME_EMAIL
  read -rp "Nom du magasin [MM Store] : " STORE_NAME
  umask 077
  cat > .env <<ENV
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL
STORE_NAME=${STORE_NAME:-MM Store}
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 48)
ENV
  echo "   .env créé (mots de passe générés au hasard, lisibles seulement par root)."
else
  echo "   .env existe déjà : conservé."
fi
source .env

echo "== 4/6 Démarrage (la première fois prend quelques minutes)"
$COMPOSE up -d --build
echo -n "   Attente de l'application"
for _ in $(seq 1 60); do
  if $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null; then
    echo " : OK"; break; fi
  echo -n "."; sleep 3
done

echo "== 5/6 Compte du gérant"
if $COMPOSE exec -T api python -c "
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User
import sys
with SessionLocal() as db: sys.exit(0 if db.scalar(select(User).where(User.role == 'admin')) else 1)" 2>/dev/null; then
  echo "   Un gérant existe déjà."
else
  read -rp "Email du gérant : " ADMIN_EMAIL
  read -rp "Nom du gérant : " ADMIN_NAME
  $COMPOSE exec api python -m app.cli create-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
fi

echo "== 6/6 Sauvegarde automatique chaque nuit à 3 h"
chmod +x deploy/*.sh
echo "0 3 * * * root $(pwd)/deploy/backup.sh >> /var/log/mmstore-backup.log 2>&1" > /etc/cron.d/mmstore-backup
deploy/backup.sh

cat <<DONE

✅ MM Store est en ligne : https://$DOMAIN
   (si le navigateur affiche une erreur de certificat, attendez 1 à 2 minutes : Caddy est en train de l'obtenir)
   Sauvegardes : /opt/mmstore-backups (chaque nuit à 3 h, 30 jours gardés)
   Mise à jour plus tard : bash deploy/update.sh
DONE
