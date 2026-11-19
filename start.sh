#!/bin/bash
# Démarrage local : installe tout la première fois, puis lance le serveur sur http://localhost:8000
set -e
cd "$(dirname "$0")"

# 1. Find a Python 3.10+ (macOS's built-in python3 is 3.9, too old). VS Code tasks don't load conda's
#    shell setup, so also look where conda, pyenv, uv, Homebrew and python.org install Python.
candidates=(python3.13 python3.12 python3.11 python3.10)
if [ -f "$HOME/.conda/environments.txt" ]; then
  while IFS= read -r env; do [ -n "$env" ] && candidates+=("$env/bin/python3"); done < "$HOME/.conda/environments.txt"
fi
for pattern in "$HOME"/miniconda3/bin/python3 "$HOME"/anaconda3/bin/python3 "$HOME"/miniforge3/bin/python3 "$HOME"/opt/*conda*/bin/python3 \
               /opt/*conda*/bin/python3 /opt/homebrew/*conda*/bin/python3 /opt/homebrew/Caskroom/*conda*/*/*/bin/python3 /usr/local/*conda*/bin/python3 \
               /opt/homebrew/bin/python3* /usr/local/bin/python3* "$HOME"/.pyenv/versions/*/bin/python3 \
               "$HOME"/.local/share/uv/python/*/bin/python3 "$HOME"/.local/bin/python3* \
               /Library/Frameworks/Python.framework/Versions/3.1*/bin/python3; do
  for f in $pattern; do [ -x "$f" ] && candidates+=("$f"); done
done
candidates+=(python3)
PY=""
for candidate in "${candidates[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Python 3.10 ou plus récent est introuvable."
  echo "   Installez Python 3.12 depuis https://www.python.org/downloads/ puis relancez (Terminal > Run Build Task)."
  echo "   Pythons trouvés :"; for c in "${candidates[@]}"; do command -v "$c" >/dev/null 2>&1 && echo "   - $c : $("$c" --version 2>&1)"; done
  exit 1
fi
echo "✅ Python utilisé : $PY ($("$PY" --version))"

# 2. Packages: installed the first time, and again whenever requirements*.txt change
if [ ! -x .venv/bin/python ]; then
  echo "📦 Installation (première fois, 1 à 2 minutes)…"
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
fi
REQ_HASH="$(cat requirements.txt requirements-dev.txt | shasum | cut -d' ' -f1)"
if [ "$(cat .venv/.requirements-hash 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "📦 Mise à jour des composants…"
  .venv/bin/pip install --quiet -r requirements-dev.txt
  echo "$REQ_HASH" > .venv/.requirements-hash
fi

# 3. Database: apply migrations, then create the demo accounts and products if they don't exist yet
export PYTHONTZPATH=""
export STORE_NAME="MM Store"
.venv/bin/alembic upgrade head
.venv/bin/python -W ignore -m app.cli create-admin --email gerant@boutique.ma --name "Gérant" --password "gerant-2026" 2>/dev/null || true
.venv/bin/python -W ignore -m app.cli seed-demo 2>/dev/null || true

echo ""
echo "======================================================================"
echo "  🚀 MM Store est prêt :  http://localhost:8000"
echo "  Admin   : gerant@boutique.ma  /  gerant-2026"
echo "  Vendeur : vendeur@demo.ma     /  vendeur123"
echo "  Documentation API : http://localhost:8000/docs"
echo "  Arrêter le serveur : Ctrl+C dans ce terminal"
echo "======================================================================"
exec .venv/bin/python -W ignore -m uvicorn app.main:app --reload --port 8000
