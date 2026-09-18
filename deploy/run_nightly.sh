#!/usr/bin/env bash
# Nightly entrypoint: used by cron, systemd or Windows Task Scheduler.
# Loads secrets from .env, makes sure Ollama is up, runs the pipeline, logs everything.
set -euo pipefail

SCOUT_HOME="${SCOUT_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCOUT_CONFIG="${SCOUT_CONFIG:-$SCOUT_HOME/config.yaml}"
cd "$SCOUT_HOME"

mkdir -p data
exec >>data/nightly.log 2>&1
echo "=== $(date -Is) run start ==="

# Secrets live in .env, never in config.yaml (which only reads ${VAR}).
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi

# Cron gives a bare PATH; make sure user-installed tools are reachable.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
if command -v ollama >/dev/null 2>&1; then
  if ! curl -sf --max-time 3 "$OLLAMA_HOST_URL/api/tags" >/dev/null; then
    echo "starting ollama..."
    nohup ollama serve >>data/ollama.log 2>&1 &
    for _ in {1..30}; do
      curl -sf --max-time 2 "$OLLAMA_HOST_URL/api/tags" >/dev/null && break
      sleep 1
    done
  fi
fi

# `scout` exists after `uv pip install -e .`; fall back to the module otherwise.
if [[ -x "$SCOUT_HOME/.venv/bin/scout" ]]; then
  "$SCOUT_HOME/.venv/bin/scout" run --config "$SCOUT_CONFIG"
else
  "$SCOUT_HOME/.venv/bin/python" -m scout.cli run --config "$SCOUT_CONFIG"
fi
status=$?
echo "=== $(date -Is) run end (exit $status) ==="
exit $status
