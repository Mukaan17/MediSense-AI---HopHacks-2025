# -*- coding: utf-8 -*-
"""Batch inference endpoints (text, image, multimodal, structured)."""

import json
import logging
from typing import List, Dict, Any

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
)

from core.extract import extractor_generate
from core.answer import answerer_generate
from core.retriever import (
    render_docs,
)
from core.fusion import fuse
from core.evidence_engine import build_evidence
from core.domains import bucket_domains
from core.diagnosis import (
    generate_structured_differential_diagnosis, analyze_risk_factors,
    generate_red_flag_alerts, generate_brief_diagnosis_summary,
)
from core.ehr_integration import create_ehr_integration_summary

log = logging.getLogger("api")

from api.settings import (
    MAX_CTX_CHARS,
)
from api.state import (
    _ehr_for_patient,
    _normalize_image_relpath,
    _predict_image_with_fallback,
    _resolve_ehr_from_uploaded_image,
    _retriever_instance,
)
from api.guards import (
    _call_llm,
)
from api.schemas import (
    InferRequest,
)
from api.pipeline import (
    _confidence_and_margin,
    _derive_summary,
    _gated_questions,
    _scan_text_findings,
    _summarize_ehr,
)

router = APIRouter()

@router.post("/infer")
def infer(req: InferRequest):
    """Conversation-only flow (no image)."""
    conversation = "\n".join(req.utterances or [])
    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever_instance().get_relevant_documents(q)
    ctx = render_docs(docs)
    # Add EHR context if patient_id provided
    ehr = _ehr_for_patient(req.patient_id)
    ctx = (_summarize_ehr(ehr) if ehr else "") + (ctx[:MAX_CTX_CHARS] if ctx else "")
    answer = _call_llm(answerer_generate, extraction, ctx)
    return {
        "extraction": extraction,
        "answer": answer,
        "ehr": (ehr or None),
        "summary": _derive_summary(advisory=answer),
    }

@router.post("/image_infer")
async def image_infer(file: UploadFile = File(...)):
    """Image-only flow, returns image findings."""
    raw = await file.read()
    preds = _predict_image_with_fallback(raw, file.filename)
    return {"image_findings": preds, "filename": file.filename}

@router.post("/quick_analysis")
async def quick_analysis(
    payload: str = Form(None),
    file: UploadFile = File(None)
):
    """
    Return only potential issues with scores (top-k fused candidates).
    Accepts optional utterances + optional image; fuses and returns a compact list.
    """
    utterances: List[str] = []
    try:
        if payload:
            data = json.loads(payload)
            utterances = data.get("utterances", []) or []
    except Exception:
        pass

    conversation = "\n".join(utterances)
    extraction = extractor_generate(conversation) if utterances else {"extracted": {}}
    text_findings = _scan_text_findings(extraction.get("extracted", {}) or {})

    image_findings: List[Dict[str, Any]] = []
    if file is not None:
        blob = await file.read()
        try:
            image_findings = _predict_image_with_fallback(blob, file.filename)
        except HTTPException:
            image_findings = []

    ranked = fuse(image_findings, text_findings, topk=10)
    # Return minimal: potential issues with scores
    return {
        "potential_issues": [
            {"condition": r.get("condition"), "score": r.get("score", 0.0)} for r in ranked
        ]
    }

@router.post("/infer_from_image_only")
async def infer_from_image_only(file: UploadFile = File(...)):
    """
    Image-only flow that tries to bind EHR:
    1) match by filename → EHR
    2) else match by top predicted label → first EHR with same chexpert_label
    """
    raw = await file.read()
    preds = _predict_image_with_fallback(raw, file.filename)
    ehr = _resolve_ehr_from_uploaded_image(raw, file.filename, preds)

    return {"image_findings": preds, "ehr": ehr, "filename": file.filename}

@router.post("/structured_diagnosis")
async def structured_diagnosis(
    payload: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Enhanced structured differential diagnosis with risk factors, red flags, and EHR integration
    """
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'payload' form field")

    utterances: List[str] = data.get("utterances", []) or []
    conversation = "\n".join(utterances)
    patient_id = data.get("patient_id")

    # EHR by patient_id (hint), may be overridden by image filename match if present
    ehr = _ehr_for_patient(patient_id)

    # 1) Extraction
    extraction = extractor_generate(conversation)
    extracted = extraction.get("extracted", {}) or {}

    # 2) Retrieval
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever_instance().get_relevant_documents(q)
    ctx = render_docs(docs)

    # 3) Imaging (optional)
    image_findings: List[Dict[str, Any]] = []
    filename = None
    if file is not None:
        blob = await file.read()
        filename = _normalize_image_relpath(file.filename) if file.filename else None
        image_findings = _predict_image_with_fallback(blob, file.filename)
        img_ehr = _resolve_ehr_from_uploaded_image(blob, file.filename, image_findings)
        if img_ehr:
            ehr = img_ehr

    # 4) Text findings from extraction
    text_findings = _scan_text_findings(extracted)

    # 5) Fusion
    ranked = fuse(image_findings, text_findings, topk=10)
    evidence = build_evidence(
        image_findings=image_findings,
        text_findings=text_findings,
        ehr=ehr,
        extracted=extracted,
        fused_ranked=ranked,
        topk=10,
    )
    ranked = (evidence.get("posterior_shift") or {}).get("adjusted_top10") or ranked
    final = ranked[0] if ranked else None
    domains = bucket_domains([r["condition"] for r in ranked]) if ranked else {}

    # 6) Generate structured differential diagnosis + brief summary
    structured_diagnosis = _call_llm(generate_structured_differential_diagnosis, 
        extraction, ctx, ehr, ranked
    )
    brief_summary = generate_brief_diagnosis_summary(extraction, ranked, max_sentences=2)

    # 7) Generate additional risk analysis
    risk_factors = analyze_risk_factors(extraction, ehr)
    red_flag_alerts = generate_red_flag_alerts(extraction, ehr, ranked)

    # 8) Create EHR integration summary
    ehr_integration = create_ehr_integration_summary(structured_diagnosis, ehr)

    # 9) Live questions (confidence-gated; degrades to [] on LLM failure)
    top_conf, margin = _confidence_and_margin(ranked)
    questions = _gated_questions(ranked, top_conf, margin, image_findings, ehr,
                                 text_findings, extracted, ctx)

    return {
        "filename": filename,
        "ehr": ehr,
        "image_findings": image_findings,
        "text_findings": text_findings,
        "domains": domains,
        "fusion": {
            "top10": ranked,
            "final_suggested_issue": final,
            "top_confidence": top_conf,
            "margin": margin
        },
        "evidence": evidence,
        "summary": brief_summary,
        "structured_diagnosis": structured_diagnosis,
        "risk_analysis": {
            "risk_factors": risk_factors,
            "red_flag_alerts": red_flag_alerts
        },
        "ehr_integration": ehr_integration,
        "coach": {"suggested": questions}
    }

@router.post("/test_structured_diagnosis")
async def test_structured_diagnosis(
    payload: str = Form(...)
):
    """
    Simplified test endpoint for structured diagnosis
    """
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'payload' form field")

    utterances: List[str] = data.get("utterances", []) or []
    conversation = "\n".join(utterances)
    patient_id = data.get("patient_id")

    # EHR by patient_id (hint)
    ehr = _ehr_for_patient(patient_id)

    # Simple extraction
    extraction = extractor_generate(conversation)
    
    # Generate structured differential diagnosis with minimal context
    structured_diagnosis = _call_llm(generate_structured_differential_diagnosis, 
        extraction, "test context", ehr, []
    )

    return {
        "structured_diagnosis": structured_diagnosis,
        "ehr": ehr,
        "extraction": extraction
    }

@router.post("/multimodal_infer")
async def multimodal_infer(
    payload: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Full flow:
    - Conversation (payload.utterances)
    - Optional patient_id hint
    - Optional image upload
    - Fuse image + text + EHR
    - RAG advisory + live questions when low confidence
    """
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'payload' form field")

    utterances: List[str] = data.get("utterances", []) or []
    conversation = "\n".join(utterances)
    patient_id = data.get("patient_id")

    # EHR by patient_id (hint), may be overridden by image filename match if present
    ehr = _ehr_for_patient(patient_id)

    # 1) Extraction
    extraction = extractor_generate(conversation)
    extracted = extraction.get("extracted", {}) or {}

    # 2) Retrieval
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever_instance().get_relevant_documents(q)
    ctx = render_docs(docs)

    # 3) Imaging (optional)
    image_findings: List[Dict[str, Any]] = []
    filename = None
    if file is not None:
        blob = await file.read()
        # Normalize to basename for consistent EHR mapping
        filename = _normalize_image_relpath(file.filename) if file.filename else None
        image_findings = _predict_image_with_fallback(blob, file.filename)
        img_ehr = _resolve_ehr_from_uploaded_image(blob, file.filename, image_findings)
        if not ehr and img_ehr:
            ehr = img_ehr
        # If payload DID provide EHR and image maps to a different patient, keep payload's EHR
        elif ehr and img_ehr and ehr.get("patient_id") != img_ehr.get("patient_id"):
            log.info(
                f"[EHR] Image maps to {img_ehr.get('patient_id')} but payload patient_id={ehr.get('patient_id')} provided; keeping payload EHR"
            )

    # 4) Text findings from extraction
    text_findings = _scan_text_findings(extracted)

    # 5) Fusion + deterministic evidence-shift posterior
    ranked = fuse(image_findings, text_findings, topk=10)
    evidence = build_evidence(
        image_findings=image_findings,
        text_findings=text_findings,
        ehr=ehr,
        extracted=extracted,
        fused_ranked=ranked,
        topk=10,
    )
    adjusted_ranked = (evidence.get("posterior_shift") or {}).get("adjusted_top10") or ranked
    ranked = adjusted_ranked
    final = ranked[0] if ranked else None

    names = [str(r.get("condition", "")) for r in ranked if r.get("condition")]
    domains = bucket_domains(names) if names else {}

    # 6) Context assembly (EHR summary + fused header + retrieved KB)
    fused_header = ""
    if ranked:
        fused_header = "Source=FUSED §Top candidates\n" + "\n".join([
            f"{i+1}. {r['condition']} ({r.get('score', 0.0):.2f}) – {r.get('why','')}"
            for i, r in enumerate(ranked)
        ]) + "\n\n"

    ehr_ctx = _summarize_ehr(ehr) if ehr else ""
    ctx_full = (ehr_ctx + fused_header + (ctx or ""))[:MAX_CTX_CHARS]

    # 7) Advisory RAG
    advisory = _call_llm(answerer_generate, extraction, ctx_full)

    # 8) Live questions (confidence-gated; degrades to [] on LLM failure)
    top_conf, margin = _confidence_and_margin(ranked)
    questions = _gated_questions(ranked, top_conf, margin, image_findings, ehr,
                                 text_findings, extracted, ctx)

    return {
        "filename": filename,
        "ehr": ehr,
        "image_findings": image_findings,
        "text_findings": text_findings,
        "domains": domains,
        "fusion": {
            "top10": ranked,
            "final_suggested_issue": final,
            "top_confidence": top_conf,
            "margin": margin
        },
        "evidence": evidence,
        "rag_advisory": advisory,
        "summary": _derive_summary(advisory=advisory, ranked=ranked),
        "coach": {"suggested": questions}
    }
