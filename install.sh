#!/usr/bin/env bash
# DANTE — installazione nel container/host di destinazione.
# Idempotente: puoi rilanciarlo. NON tocca le config già compilate.
set -euo pipefail
cd "$(dirname "$0")"

echo "== DANTE · installazione =="

# 1) Python >= 3.10 (Debian 12 = 3.11, va bene)
PYBIN="$(command -v python3.13 || command -v python3.12 || command -v python3.11 \
        || command -v python3.10 || command -v python3 || true)"
if [ -z "$PYBIN" ]; then
  echo "ERRORE: nessun python3 trovato. Installa python3 (>=3.10) e rilancia." >&2
  exit 1
fi
echo "Python: $PYBIN ($($PYBIN --version 2>&1))"

# 2) venv + dipendenze
[ -d .venv ] || "$PYBIN" -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Dipendenze Python installate."

# 3) file di config (dagli esempi, se mancano)
for f in inventory virtualizor; do
  if [ ! -f "config/$f.yaml" ]; then
    cp "config/$f.example.yaml" "config/$f.yaml"
    echo "→ Creato config/$f.yaml : COMPILALO con i dati reali."
  fi
done
chmod 600 config/*.yaml 2>/dev/null || true   # i segreti restano leggibili solo dall'utente

# 4) controlli ambiente
command -v claude >/dev/null 2>&1 \
  && echo "CLI claude: $(claude --version 2>&1 | head -1)" \
  || echo "ATTENZIONE: CLI 'claude' non trovata → installa: npm i -g @anthropic-ai/claude-code"
if [ -f .env ] && grep -qE '^(CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY)=.+' .env; then
  echo "Auth: configurata nel file .env"
else
  echo "ATTENZIONE: auth non configurata. Crea .env con CLAUDE_CODE_OAUTH_TOKEN (abbonamento) o ANTHROPIC_API_KEY."
fi

echo
echo "Fatto. Prossimi passi:"
echo "  1) Compila config/inventory.yaml e config/virtualizor.yaml"
echo "  2) Crea .env con CLAUDE_CODE_OAUTH_TOKEN (da 'claude setup-token' sul Mac)"
echo "  3) Verifica rete verso la 4085 (whitelist IP o WireGuard)"
echo "  4) ./.venv/bin/python -m agent.dante"
