# -*- coding: utf-8 -*-
"""Case history: durable listings and per-case timelines. Available when
the persistence layer is active (CASE_DB_URL); other deployments get an
explicit 503, never a silent empty list."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger("api")

from api.state import (
    _case_store,
)
from api.responses import (
    CaseListResponse,
    TimelineResponse,
)

router = APIRouter()


def _durable_store():
    if getattr(_case_store, "list_cases", None) is None:
        raise HTTPException(
            status_code=503,
            detail="Case history requires the durable case store (set CASE_DB_URL)")
    return _case_store


@router.get("/api/cases", response_model=CaseListResponse)
def list_cases(patient_id: Optional[str] = Query(None),
               limit: int = Query(50, ge=1, le=200),
               offset: int = Query(0, ge=0)):
    store = _durable_store()
    cases = store.list_cases(patient_id=patient_id, limit=limit, offset=offset)
    return {"cases": cases, "count": len(cases)}


@router.get("/api/case/{case_id}/timeline", response_model=TimelineResponse)
def case_timeline(case_id: str):
    store = _durable_store()
    if not store.exists(case_id):
        raise HTTPException(status_code=404, detail="case_id not found")
    events = store.get_timeline(case_id)
    return {"case_id": case_id, "events": events, "count": len(events)}
