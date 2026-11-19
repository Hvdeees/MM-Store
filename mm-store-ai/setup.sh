#!/bin/bash
# Installs MM Store AI on this computer and prints the settings to paste into the Claude desktop app.
set -e
cd "$(dirname "$0")"

# 1. A Python 3.10+ (same search as MM Store's start.sh: macOS's own python3 is too old)
candidates=(python3.13 python3.12 python3.11 python3.10)
[ -f "$HOME/.conda/environments.txt" ] && while IFS= read -r env; do [ -n "$env" ] && candidates+=("$env/bin/python3"); done < "$HOME/.conda/environments.txt"
for pattern in "$HOME"/miniconda3/bin/python3 "$HOME"/anaconda3/bin/python3 /opt/homebrew/bin/python3* /usr/local/bin/python3* \
               "$HOME"/pinokio/bin/miniconda/bin/python3 "$HOME"/.pyenv/versions/*/bin/python3 /Library/Frameworks/Python.framework/Versions/3.1*/bin/python3; do
  for f in $pattern; do [ -x "$f" ] && candidates+=("$f"); done
done
PY=""
for c in "${candidates[@]}" python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "❌ Python 3.10+ introuvable : installez-le depuis https://www.python.org/downloads/"; exit 1; }
echo "✅ Python : $PY ($("$PY" --version))"

# 2. Its own virtual environment, with the tests' needs (MM Store's packages, to run the real app in tests)
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"
[ -f ../boutique-manager/requirements.txt ] && .venv/bin/pip install --quiet -r ../boutique-manager/requirements.txt
echo "✅ Installé."

# 3. The settings for the Claude desktop app
cat <<JSON

Collez ceci dans la configuration MCP de l'app Claude (remplacez l'email et le mot de passe
par ceux du compte « Assistant IA » créé dans MM Store, page Équipe) :

{
  "mcpServers": {
    "mm-store": {
      "command": "$(pwd)/.venv/bin/python",
      "args": ["-m", "mmstore_ai"],
      "env": {
        "MMSTORE_URL": "http://localhost:8000",
        "MMSTORE_EMAIL": "assistant@mmstore.ma",
        "MMSTORE_PASSWORD": "mot-de-passe-de-l-assistant"
      }
    }
  }
}
JSON
