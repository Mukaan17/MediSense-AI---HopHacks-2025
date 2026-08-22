# -*- coding: utf-8 -*-
"""Live-case REST lifecycle: creation, transcribe step, finalize report.
The two WebSocket endpoints live in routes/ws.py."""

import logging
import asyncio
import uuid

from fastapi import (
    APIRouter, UploadFile, File, HTTPException, Query,
)

from core.extract import extractor_generate
from core.answer import answerer_generate
from core.retriever import (
    render_docs,
)
from core.fusion import fuse
from core.evidence_engine import build_evidence
from core.domains import bucket_domains
from core.questioner_llm import (
    propose_questions_llm,
)
from core.llm_client import (
    anthropic_available, invoke_claude_full, get_llm,
    get_final_model, get_fallback_final_model,
)

log = logging.getLogger("api")

from api.settings import (
    ASK_THRESH,
    MARGIN_THRESH,
    MAX_CTX_CHARS,
)
from api.state import (
    ALIASES,
    _case_store,
    _normalize_image_relpath,
    _predict_image_with_fallback,
    _resolve_ehr_from_uploaded_image,
    _retriever_instance,
)
from api.guards import (
    _call_llm,
)
from api.schemas import (
    TranscribeIn,
)
from api.pipeline import (
    FINAL_REPORT_SYSTEM,
    _compact_live,
    _confidence_and_margin,
    _final_report_prompt,
    _recompute_case,
    _scan_text_findings,
    _scope_hint,
    _summarize_ehr,
)

router = APIRouter()

@router.post("/api/case/voice")
async def create_voice_case(
    live: bool = Query(True),
    max_candidates: int = Query(3, ge=1, le=5),
    min_conf: float = Query(0.60, ge=0.0, le=1.0),
):
    """Create a case for voice-only transcription (no image)"""
    # No image processing for voice-only cases
    preds = []
    filename = None
    ehr = None
    
    # Fuse empty image findings with empty text findings
    ranked = fuse(preds, [], topk=10)
    top_conf, margin = _confidence_and_margin(ranked)

    normalized = []
    for r in (ranked or []):
        c = r.get("condition")
        if not c: continue
        normalized.append(ALIASES.get(c, c.lower().replace(" ", "_")))
    domains = bucket_domains(normalized) if normalized else {}

    case_id = str(uuid.uuid4())
    _case_store.put(case_id, {
        "filename": filename,
        "image_findings": preds,
        "ehr": ehr,
        "ranked": ranked,
        "domains": domains,
        "utterances": [],
    })

    if live:
        return {"case_id": case_id, **_compact_live(ranked, top_conf, margin, ehr, [], max_candidates, min_conf, None)}
    return {"case_id": case_id, "filename": filename, "ehr": ehr, "image_findings": preds,
            "fusion": {"top10": ranked, "top_confidence": top_conf, "margin": margin},
            "domains": domains}

@router.post("/api/case")
async def create_case(
    live: bool = Query(True),
    max_candidates: int = Query(3, ge=1, le=5),
    min_conf: float = Query(0.60, ge=0.0, le=1.0),
    file: UploadFile = File(None)
):
    # Handle optional image upload
    preds = []
    filename = None
    ehr = None
    
    if file is not None:
        raw = await file.read()
        preds = _predict_image_with_fallback(raw, file.filename)  # [{"label": "...", "score": 0.xx}, ...]
        for p in preds:
            if "prob" not in p and "score" in p:
                p["prob"] = float(p["score"])

        filename = _normalize_image_relpath(file.filename) if file.filename else None
        ehr = _resolve_ehr_from_uploaded_image(raw, file.filename, preds)

    # Fuse image findings with empty text findings (no conversation yet)
    ranked = fuse(preds, [], topk=10)
    top_conf, margin = _confidence_and_margin(ranked)

    normalized = []
    for r in (ranked or []):
        c = r.get("condition")
        if not c: continue
        normalized.append(ALIASES.get(c, c.lower().replace(" ", "_")))
    domains = bucket_domains(normalized) if normalized else {}

    case_id = str(uuid.uuid4())
    _case_store.put(case_id, {
        "filename": filename,
        "image_findings": preds,
        "ehr": ehr,
        "ranked": ranked,
        "domains": domains,
        "utterances": [],
    })

    if live:
        return {"case_id": case_id, **_compact_live(ranked, top_conf, margin, ehr, [], max_candidates, min_conf, None)}
    return {"case_id": case_id, "filename": filename, "ehr": ehr, "image_findings": preds,
            "fusion": {"top10": ranked, "top_confidence": top_conf, "margin": margin},
            "domains": domains}

@router.post("/api/case/{case_id}/transcribe")
def transcribe_step(
    case_id: str,
    body: TranscribeIn,
    live: bool = Query(True),
    max_candidates: int = Query(3, ge=1, le=5),
    min_conf: float = Query(0.60, ge=0.0, le=1.0),
    min_margin: float = Query(0.03, ge=0.0, le=0.2)
):
    case = _case_store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case_id not found")

    case["utterances"].append(body.utterance)
    _case_store.put(case_id, case)
    conversation = "\n".join(case["utterances"])

    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever_instance().get_relevant_documents(q)
    ctx = render_docs(docs) or ""

    extracted = extraction.get("extracted", {}) or {}
    text_findings = _scan_text_findings(extracted)
    ranked = fuse(case["image_findings"], text_findings, topk=10)
    evidence = build_evidence(
        image_findings=case["image_findings"],
        text_findings=text_findings,
        ehr=case.get("ehr"),
        extracted=extracted,
        fused_ranked=ranked,
        topk=10,
    )
    ranked = (evidence.get("posterior_shift") or {}).get("adjusted_top10") or ranked
    final = ranked[0] if ranked else None
    top_conf, margin = _confidence_and_margin(ranked)

    normalized = []
    for r in (ranked or []):
        c = r.get("condition")
        if not c: continue
        normalized.append(ALIASES.get(c, c.lower().replace(" ", "_")))
    domains = bucket_domains(normalized) if normalized else {}

    fused_header = ""
    if ranked:
        fused_header = "Source=FUSED §Top candidates\n" + "\n".join(
            [f"{i+1}. {r['condition']} ({r.get('score',0.0):.2f}) – {r.get('why','')}" for i, r in enumerate(ranked)]
        ) + "\n\n"
    ehr_ctx = _summarize_ehr(case["ehr"]) if case["ehr"] else ""
    ctx_full = (ehr_ctx + fused_header + ctx)[:MAX_CTX_CHARS]

    advisory = _call_llm(answerer_generate, extraction, ctx_full)

    questions = []
    if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH and top_conf < 0.95):
        state = {
            "top_candidates": ranked[:5],
            "image_findings": case["image_findings"],
            "ehr_summary": case["ehr"] or {},
            "text_findings": text_findings,
            "extraction": extracted,
            "retrieved_context": ctx[:MAX_CTX_CHARS],
            "top_confidence": top_conf,
            "margin": margin,
            "scope_hint": _scope_hint(top_conf),
        }
        try:
            questions = propose_questions_llm(state, max_questions=3)
        except Exception as e:
            log.warning(f"[coach] question generation failed: {e}")

    case.update({"ranked": ranked, "domains": domains})

    if live:
        if (top_conf >= 0.95) and (margin >= min_margin):
            questions = questions[:1]
        payload = _compact_live(ranked, top_conf, margin, case["ehr"], questions, max_candidates, min_conf, None)
        payload["evidence"] = evidence
        return {"case_id": case_id, **payload}

    return {
        "case_id": case_id,
        "fusion": {"top10": ranked, "final_suggested_issue": final, "top_confidence": top_conf, "margin": margin},
        "evidence": evidence,
        "domains": domains,
        "rag_advisory": advisory,
        "coach": {"suggested": questions}
    }

@router.post("/api/case/{case_id}/finalize")
async def finalize_case(case_id: str):
    """Deep advisory report over the full conversation once a live case ends."""
    case = _case_store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case_id not found")
    utterances = case.get("utterances", [])
    if not utterances:
        raise HTTPException(status_code=400, detail="case has no utterances to summarize")

    _, _, details = await asyncio.to_thread(_recompute_case, case)
    conversation = "\n".join(utterances)
    ehr_ctx = _summarize_ehr(case.get("ehr")) if case.get("ehr") else ""
    prompt = _final_report_prompt(conversation, ehr_ctx, details["ranked"], details["ctx"])

    model_used = None
    report = None
    if anthropic_available():
        try:
            model_used = get_final_model()
            report = await invoke_claude_full(prompt, model=model_used,
                                              system=FINAL_REPORT_SYSTEM)
        except Exception as e:
            log.warning(f"[finalize] Claude report failed, falling back to Gemini: {e}")
            report = None
    if report is None:
        fallback_model = get_fallback_final_model()
        def _gemini_report() -> str:
            lm = get_llm(model=fallback_model)
            return lm.invoke(f"{FINAL_REPORT_SYSTEM}\n\n{prompt}").content
        try:
            report = await asyncio.to_thread(_gemini_report)
            model_used = fallback_model
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"No LLM available for report: {e}")

    return {
        "case_id": case_id,
        "report": report,
        "model": model_used,
        "fusion": {"top10": details["ranked"], "top_confidence": details["top_conf"],
                   "margin": details["margin"]},
        "disclaimer": "Advisory reference only - not a diagnosis. Correlate clinically.",
    }
