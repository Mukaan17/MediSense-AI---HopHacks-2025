# -*- coding: utf-8 -*-
"""Pydantic response models for the stable endpoints.

These make the OpenAPI schema a real contract (typed clients can be
generated from it) without freezing evolving payloads: models that carry
pipeline output use ``extra="allow"`` so documented keys are guaranteed
while additional fields still pass through.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

log = logging.getLogger("api")


# --------------- system ---------------

class VoiceModelsStatus(BaseModel):
    whisperx_model_loaded: bool
    diarization_model_loaded: bool
    alignment_model_loaded: bool


class LLMStatus(BaseModel):
    anthropic: bool
    gemini: bool


class HealthResponse(BaseModel):
    status: str
    app_mode: str
    ehr_synthetic: bool
    case_store: str
    collection: str
    persist_dir: str
    emb_model: str
    top_k: int
    doc_count: Optional[int] = None
    ehr_loaded: int
    image_model_loaded: bool
    llm: LLMStatus
    voice_transcription: VoiceModelsStatus


class KnowledgeBaseModeResponse(BaseModel):
    mode: str
    sources: List[str]
    doc_count: Optional[int] = None
    emb_model: Optional[str] = None
    built_at: Optional[str] = None
    last_updated: Optional[str] = None
    description: str


class ReloadEhrResponse(BaseModel):
    ehr_loaded: int
    ehr_source: str


class ReloadRetrieverResponse(BaseModel):
    status: str
    doc_count_before: int


# --------------- auth ---------------

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    expires_in_minutes: int
    csrf_token: Optional[str] = None


class LogoutResponse(BaseModel):
    status: str


class MeResponse(BaseModel):
    username: str
    role: str
    # False in demo mode (anonymous demo user), True for a real session.
    authenticated: bool


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int


# --------------- EHR ---------------

class EHRDemographics(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None


class EHRPatientSummary(BaseModel):
    patient_id: Optional[str] = None
    demographics: EHRDemographics
    vital_signs: Optional[Dict[str, Any]] = None
    pmh: List[str] = []
    meds: List[str] = []
    allergies: List[str] = []


class EHRPatientsResponse(BaseModel):
    patients: List[EHRPatientSummary]
    total: int
    data_source: str


class EHRPatientDetailResponse(BaseModel):
    patient: Dict[str, Any]


# --------------- cases ---------------

class CaseCreateResponse(BaseModel):
    """Case creation returns the compact live HUD (live=1) or the full
    fusion payload; only case_id is invariant across both shapes."""
    model_config = ConfigDict(extra="allow")

    case_id: str


class FusionSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    top10: List[Dict[str, Any]]
    top_confidence: float
    margin: float


class FinalizeCaseResponse(BaseModel):
    """Inline mode returns the full report (status='complete'); queue mode
    returns status='queued' and the client polls /api/case/{id}/report."""
    case_id: str
    status: str = "complete"
    report: Optional[str] = None
    model: Optional[str] = None
    fusion: Optional[FusionSummary] = None
    disclaimer: str


class ReportStatusResponse(BaseModel):
    case_id: str
    status: str  # queued | running | complete | error
    report: Optional[str] = None
    model: Optional[str] = None
    fusion: Optional[FusionSummary] = None
    disclaimer: Optional[str] = None
    error: Optional[str] = None
