#!/usr/bin/env bash
# Starts the backend for E2E runs. APP_MODE=demo (default) or clinical;
# clinical mode provisions a throwaway users file + secret for the run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

export APP_MODE="${APP_MODE:-demo}"
export FRONTEND_ORIGINS="${FRONTEND_ORIGINS:-http://localhost:3080,http://127.0.0.1:3080}"

if [ "$APP_MODE" = "clinical" ]; then
  E2E_DIR="$(mktemp -d)"
  export AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')}"
  export AUTH_USERS_FILE="$E2E_DIR/users.json"
  "$PYTHON" - <<'PYEOF'
import json, os
from core.auth import hash_password
with open(os.environ["AUTH_USERS_FILE"], "w") as f:
    json.dump({"e2edoc": {"password_hash": hash_password("E2e-pass-123"),
                          "role": "clinician"}}, f)
print(f"e2e users file: {os.environ['AUTH_USERS_FILE']}")
PYEOF
fi

exec "$PYTHON" -m uvicorn api.server:app --port "${E2E_API_PORT:-8000}" --log-level warning
