# -*- coding: utf-8 -*-
"""Uploaded-audio endpoints (WhisperX transcription + inference)."""

import logging
from typing import List, Dict, Any, Optional

from fastapi import (
    APIRouter, UploadFile, File, HTTPException,
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
from core.voice_transcription import voice_service

log = logging.getLogger("api")

from api.settings import (
    ASK_THRESH,
    MARGIN_THRESH,
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
from api.pipeline import (
    _confidence_and_margin,
    _derive_summary,
    _scan_text_findings,
    _scope_hint,
    _summarize_ehr,
)

router = APIRouter()

@router.post("/voice_transcribe")
async def voice_transcribe(
    file: UploadFile = File(...),
    description: str = None
):
    """
    Transcribe audio file using WhisperX and return formatted conversation data
    """
    try:
        # Validate file type
        if file.content_type and not file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Read file content
        file_content = await file.read()
        
        # Transcribe using voice service
        result = voice_service.transcribe_file(file_content, file.filename, description)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error during voice transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Voice transcription failed: {str(e)}")

@router.post("/voice_infer")
async def voice_infer(
    file: UploadFile = File(...),
    patient_id: Optional[str] = None,
    description: str = None
):
    """
    Voice-based inference: Transcribe audio and run through full clinical pipeline
    """
    try:
        # Validate file type
        if file.content_type and not file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # 1) Transcribe audio
        file_content = await file.read()
        transcription_result = voice_service.transcribe_file(file_content, file.filename, description)
        
        # 2) Extract utterances from transcription
        utterances = []
        for entry in transcription_result.conversation:
            for utterance in entry.utterances:
                utterances.append(utterance.text)
        
        if not utterances:
            raise HTTPException(status_code=400, detail="No speech detected in audio file")
        
        # 3) Run through existing inference pipeline
        conversation = "\n".join(utterances)
        patient_id = patient_id
        
        # EHR by patient_id (hint)
        ehr = _ehr_for_patient(patient_id)
        
        # 4) Extraction
        extraction = extractor_generate(conversation)
        extracted = extraction.get("extracted", {}) or {}
        
        # 5) Retrieval
        q = extraction.get("retrieval_query") or conversation
        docs = _retriever_instance().get_relevant_documents(q)
        ctx = render_docs(docs)
        
        # 6) Text findings from extraction
        text_findings = _scan_text_findings(extracted)
        
        # 7) Fusion (no image findings for voice-only) + evidence shift, so
        # this endpoint's response carries the same posterior_shift
        # explainability as every other inference route
        image_findings: List[Dict[str, Any]] = []
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

        # 8) Context assembly
        fused_header = ""
        if ranked:
            fused_header = "Source=FUSED §Top candidates\n" + "\n".join([
                f"{i+1}. {r['condition']} ({r.get('score', 0.0):.2f}) – {r.get('why','')}"
                for i, r in enumerate(ranked)
            ]) + "\n\n"
        
        ehr_ctx = _summarize_ehr(ehr) if ehr else ""
        ctx_full = (ehr_ctx + fused_header + (ctx or ""))[:MAX_CTX_CHARS]
        
        # 9) Advisory RAG
        advisory = _call_llm(answerer_generate, extraction, ctx_full)
        
        # 10) Live questions (confidence-gated)
        top_conf, margin = _confidence_and_margin(ranked)
        questions = []
        if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH):
            state = {
                "top_candidates": ranked[:5],
                "image_findings": image_findings,
                "ehr_summary": ehr or {},
                "text_findings": text_findings,
                "extraction": extracted,
                "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
                "top_confidence": top_conf,
                "margin": margin,
                "scope_hint": _scope_hint(top_conf),
            }
            try:
                questions = propose_questions_llm(state, max_questions=4)
            except Exception as e:
                log.warning(f"[coach] question generation failed: {e}")

        return {
                "transcription": transcription_result,
                "filename": file.filename,
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
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error during voice inference: {e}")
        raise HTTPException(status_code=500, detail=f"Voice inference failed: {str(e)}")

@router.post("/multimodal_voice_infer")
async def multimodal_voice_infer(
    audio_file: UploadFile = File(...),
    image_file: UploadFile = File(None),
    patient_id: Optional[str] = None,
    description: str = None
):
    """
    Full multimodal inference with voice + image:
    - Transcribe audio conversation
    - Analyze uploaded image (optional)
    - Fuse voice + image + EHR
    - RAG advisory + live questions when low confidence
    """
    try:
        # Validate audio file type
        if audio_file.content_type and not audio_file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="Audio file must be an audio file")
        
        # 1) Transcribe audio
        audio_content = await audio_file.read()
        transcription_result = voice_service.transcribe_file(audio_content, audio_file.filename, description)
        
        # 2) Extract utterances from transcription
        utterances = []
        for entry in transcription_result.conversation:
            for utterance in entry.utterances:
                utterances.append(utterance.text)
        
        if not utterances:
            raise HTTPException(status_code=400, detail="No speech detected in audio file")
        
        # 3) Process conversation
        conversation = "\n".join(utterances)
        
        # EHR by patient_id (hint), may be overridden by image filename match if present
        ehr = _ehr_for_patient(patient_id)
        
        # 4) Extraction
        extraction = extractor_generate(conversation)
        extracted = extraction.get("extracted", {}) or {}
        
        # 5) Retrieval
        q = extraction.get("retrieval_query") or conversation
        docs = _retriever_instance().get_relevant_documents(q)
        ctx = render_docs(docs)
        
        # 6) Imaging (optional)
        image_findings: List[Dict[str, Any]] = []
        image_filename = None
        if image_file is not None:
            blob = await image_file.read()
            image_filename = _normalize_image_relpath(image_file.filename) if image_file.filename else None
            image_findings = _predict_image_with_fallback(blob, image_file.filename)
            img_ehr = _resolve_ehr_from_uploaded_image(blob, image_file.filename, image_findings)
            if img_ehr:
                ehr = img_ehr
        
        # 7) Text findings from extraction
        text_findings = _scan_text_findings(extracted)
        
        # 8) Fusion + deterministic evidence-shift posterior
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
        domains = bucket_domains([r["condition"] for r in ranked]) if ranked else {}
        
        # 9) Context assembly (EHR summary + fused header + retrieved KB)
        fused_header = ""
        if ranked:
            fused_header = "Source=FUSED §Top candidates\n" + "\n".join([
                f"{i+1}. {r['condition']} ({r.get('score', 0.0):.2f}) – {r.get('why','')}"
                for i, r in enumerate(ranked)
            ]) + "\n\n"
        
        ehr_ctx = _summarize_ehr(ehr) if ehr else ""
        ctx_full = (ehr_ctx + fused_header + (ctx or ""))[:MAX_CTX_CHARS]
        
        # 10) Advisory RAG
        advisory = _call_llm(answerer_generate, extraction, ctx_full)
        
        # 11) Live questions (confidence-gated)
        top_conf, margin = _confidence_and_margin(ranked)
        questions = []
        if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH):
            state = {
                "top_candidates": ranked[:5],
                "image_findings": image_findings,
                "ehr_summary": ehr or {},
                "text_findings": text_findings,
                "extraction": extracted,
                "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
                "top_confidence": top_conf,
                "margin": margin,
                "scope_hint": _scope_hint(top_conf),
            }
            try:
                questions = propose_questions_llm(state, max_questions=4)
            except Exception as e:
                log.warning(f"[coach] question generation failed: {e}")

        return {
            "transcription": transcription_result,
            "audio_filename": audio_file.filename,
            "image_filename": image_filename,
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
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error during multimodal voice inference: {e}")
        raise HTTPException(status_code=500, detail=f"Multimodal voice inference failed: {str(e)}")
