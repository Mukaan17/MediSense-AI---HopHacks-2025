#!/usr/bin/env python3
"""Export the API's OpenAPI schema to openapi.json at the repo root.

The committed schema is the machine-checked contract between backend and
frontend: CI regenerates it and fails on drift, and the frontend's
TypeScript types are generated from it (frontend: `npm run gen:api`).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from api.server import app

    schema = app.openapi()
    out = REPO_ROOT / "openapi.json"
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"[openapi] {len(schema.get('paths', {}))} paths -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
