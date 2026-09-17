#!/usr/bin/env bash
# Serves the fixture site used by config.demo.yaml on :8765.
set -euo pipefail
cd "$(dirname "$0")/../tests/fixtures/site"
exec python3 -m http.server 8765 --bind 127.0.0.1
