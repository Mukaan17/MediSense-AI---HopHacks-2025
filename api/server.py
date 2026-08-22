# -*- coding: utf-8 -*-
"""Application assembly.

Everything else in this package is a focused module:

    api/settings.py     environment-derived tunables
    api/state.py        process state (EHR indices, models, case store)
    api/guards.py       mode/LLM request guards
    api/schemas.py      request bodies
    api/pipeline.py     the shared inference pipeline
    api/middleware.py   the HTTP perimeter (auth, limits, audit, CORS)
    api/routes/         one router per endpoint group

This module wires them together and stays the stable entry point:
`uvicorn api.server:app` (and `main.py` / `run_integrated_server.py`).
"""

import threading

from core.logging_setup import configure_logging

configure_logging()

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from core.auth import validate_clinical_config
from core.error_tracking import maybe_init_sentry
from core.retriever import warm_up as retriever_warm_up
from core.secrets import hydrate_environment

# Managed secrets (AWS SM / *_FILE) become plain env vars before anything
# reads them; a no-op when the values are already in the environment.
hydrate_environment(["AUTH_SECRET_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                     "SENTRY_DSN"])

maybe_init_sentry()

from api import middleware
from api.routes import auth, cases, ehr, history, inference, system, voice, ws

# Clinical mode must never boot unsigned.
validate_clinical_config()

app = FastAPI(title="Multimodal Clinical Reference (Advisory)")

middleware.install(app)


# A backing-store outage (Redis, network) is a retryable operational
# condition: surface it as an explicit 503, never an anonymous 500.
def _install_store_outage_handler(app) -> None:
    from fastapi.responses import JSONResponse

    async def _store_unreachable(request, exc):
        return JSONResponse(
            {"detail": f"Backing store unreachable: {exc}"}, status_code=503)

    app.add_exception_handler(ConnectionError, _store_unreachable)
    try:
        import redis.exceptions as _redis_exc
        app.add_exception_handler(_redis_exc.ConnectionError, _store_unreachable)
    except ImportError:
        pass


_install_store_outage_handler(app)

# Dual-mount: every route is served at its historical root path and under
# /v1. New clients should use /v1; the root mount stays for compatibility.
for _router in (system.router, auth.router, inference.router, voice.router,
                ehr.router, cases.router, history.router, ws.router):
    app.include_router(_router)
    app.include_router(_router, prefix="/v1")


@app.on_event("startup")
async def _warm_up_models() -> None:
    # Load the vector store and cross-encoder off the request path so the
    # first live query doesn't pay model-load (or download) latency.
    threading.Thread(target=retriever_warm_up, daemon=True).start()
