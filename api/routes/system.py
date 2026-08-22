# -*- coding: utf-8 -*-
"""Operational endpoints: health, metrics, hot reloads, KB mode."""

import logging
import threading
from datetime import datetime

from fastapi import (
    APIRouter, Form,
)

from core.retriever import (
    get_doc_count, get_top_k,
    warm_up as retriever_warm_up, PERSIST_DIR, COLLECTION, EMB_MODEL,
)
from core.voice_transcription import voice_service
from core.app_mode import get_app_mode, ehr_is_synthetic
from core import metrics

log = logging.getLogger("api")

from api.settings import (
    EHR_JSON,
)
from api.state import (
    EHR_RECORDS,
    _case_store,
    _img_model,
    _load_ehr,
    reset_retriever_singleton,
)
from api.guards import (
    _demo_only,
)
from api.responses import (
    HealthResponse,
    KnowledgeBaseModeResponse,
    ReloadEhrResponse,
    ReloadRetrieverResponse,
)

router = APIRouter()

@router.get("/metrics")
def metrics_endpoint():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(metrics.render_prometheus(), media_type="text/plain; version=0.0.4")

@router.get("/health", response_model=HealthResponse)
def health():
    count = get_doc_count()
    return {
        "status": "ok",
        "app_mode": get_app_mode(),
        "ehr_synthetic": ehr_is_synthetic(EHR_JSON),
        "case_store": _case_store.backend,
        "collection": COLLECTION,
        "persist_dir": PERSIST_DIR,
        "emb_model": EMB_MODEL,
        "top_k": get_top_k(),
        "doc_count": (count if count >= 0 else None),
        "ehr_loaded": len(EHR_RECORDS),
        "image_model_loaded": _img_model is not None,
        "voice_transcription": {
            "whisperx_model_loaded": voice_service.whisperx_model is not None,
            "diarization_model_loaded": voice_service.diarize_model is not None,
            "alignment_model_loaded": voice_service.align_model is not None,
        }
    }

@router.get("/knowledge_base/mode", response_model=KnowledgeBaseModeResponse)
def get_knowledge_base_mode():
    """Get current knowledge base mode"""
    return {
        "mode": "clinical",
        "sources": ["Clinical Guidelines", "UpToDate", "PubMed"],
        "last_updated": "2024-01-01T00:00:00Z"
    }

@router.post("/knowledge_base/mode", response_model=KnowledgeBaseModeResponse)
def set_knowledge_base_mode(mode: str = Form(...)):
    """Set knowledge base mode"""
    _demo_only("Knowledge base mode toggle")
    return {
        "mode": mode,
        "sources": ["Clinical Guidelines", "UpToDate", "PubMed"],
        "last_updated": datetime.now().isoformat()
    }

@router.post("/reload_ehr", response_model=ReloadEhrResponse)
def reload_ehr():
    """Reload EHR JSON without restarting the server (optional convenience)."""
    _load_ehr()
    return {"ehr_loaded": len(EHR_RECORDS), "ehr_source": EHR_JSON}

@router.post("/reload_retriever", response_model=ReloadRetrieverResponse)
def reload_retriever():
    """Re-initialize the RAG store after a KB rebuild (init is otherwise
    once-per-process). Re-warms on a background thread."""
    count_before = get_doc_count()
    reset_retriever_singleton()
    threading.Thread(target=retriever_warm_up, daemon=True).start()
    return {"status": "reloading", "doc_count_before": count_before}
