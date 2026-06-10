#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/run_local_gemini.sh backend
#   ./scripts/run_local_gemini.sh frontend
#   ./scripts/run_local_gemini.sh smoke
#   ./scripts/run_local_gemini.sh all

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-backend}"

if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source .env
fi

warn_if_missing_key() {
  if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo "WARNING: GEMINI_API_KEY is empty in .env."
    echo "         LLM-backed endpoints will return fallback behavior."
  fi
}

run_backend() {
  warn_if_missing_key
  echo "Starting backend at http://localhost:8000 ..."
  uvicorn api.server:app --host 0.0.0.0 --port 8000
}

run_frontend() {
  echo "Starting frontend at http://localhost:3000 ..."
  cd frontend
  npm start
}

run_smoke() {
  echo "Running smoke test against http://localhost:8000 ..."
  python3 smoke_test.py --base-url http://localhost:8000
}

run_all() {
  warn_if_missing_key
  echo "Starting backend in background ..."
  uvicorn api.server:app --host 0.0.0.0 --port 8000 >/tmp/hophacks_backend.log 2>&1 &
  BACK_PID=$!
  trap 'kill "$BACK_PID" >/dev/null 2>&1 || true' EXIT
  sleep 3
  run_smoke
  echo "Backend log: /tmp/hophacks_backend.log"
  echo "Run frontend in another terminal:"
  echo "  ./scripts/run_local_gemini.sh frontend"
}

case "$MODE" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  smoke) run_smoke ;;
  all) run_all ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: $0 [backend|frontend|smoke|all]"
    exit 1
    ;;
esac
