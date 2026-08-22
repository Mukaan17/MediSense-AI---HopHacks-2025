# -*- coding: utf-8 -*-
"""Cross-cutting request guards: demo-only feature refusal, the
clinical-mode synthetic-EHR ban, and LLM-config error surfacing."""

import logging

from fastapi import (
    HTTPException,
)

from core.app_mode import is_clinical, ehr_is_synthetic

log = logging.getLogger("api")

from api.settings import (
    EHR_JSON,
)

def _demo_only(feature: str) -> None:
    """Mocked integrations exist to showcase the workflow; clinical mode
    refuses them rather than pretending they are real."""
    if is_clinical():
        raise HTTPException(
            status_code=403,
            detail=f"{feature} is a demo-mode mockup and is disabled in clinical mode.")

def _guard_synthetic_ehr() -> None:
    """Clinical mode never serves the bundled synthetic dataset (MIMIC demo
    patients paired with unrelated CheXpert images)."""
    if is_clinical() and ehr_is_synthetic(EHR_JSON):
        raise HTTPException(
            status_code=403,
            detail="Synthetic demo EHR dataset is disabled in clinical mode; configure EHR_JSON to a real data source.")

def _call_llm(fn, *args, **kwargs):
    """Run an LLM-backed step; surface a missing-key config error as an
    explicit 503 instead of an anonymous 500."""
    try:
        return fn(*args, **kwargs)
    except RuntimeError as e:
        if "API_KEY" in str(e).upper():
            raise HTTPException(status_code=503, detail=f"LLM not configured: {e}")
        raise
