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
from core.retriever import warm_up as retriever_warm_up

from api import middleware
from api.routes import auth, cases, ehr, inference, system, voice

# Clinical mode must never boot unsigned.
validate_clinical_config()

app = FastAPI(title="Multimodal Clinical Reference (Advisory)")

middleware.install(app)

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(inference.router)
app.include_router(voice.router)
app.include_router(ehr.router)
app.include_router(cases.router)


@app.on_event("startup")
async def _warm_up_models() -> None:
    # Load the vector store and cross-encoder off the request path so the
    # first live query doesn't pay model-load (or download) latency.
    threading.Thread(target=retriever_warm_up, daemon=True).start()
