#!/usr/bin/env python3
"""Thin wrapper for launching the canonical FastAPI backend."""

import sys
from pathlib import Path

import uvicorn


def main() -> None:
    if not Path("api/server.py").exists():
        print("Error: api/server.py not found. Run from project root.")
        sys.exit(1)

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
