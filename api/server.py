# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 15:49:29
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:58:04
# server.py
import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---- Core components (you already have these) ----
from core.extract import extractor_generate
from core.answer import answerer_generate
from core.retriever import (
    get_retriever, render_docs, get_doc_count, get_top_k,
    PERSIST_DIR, COLLECTION, EMB_MODEL
)
from core.imaging import ImagingModel
from core.fusion import fuse
from core.domains import bucket_domains
from core.config import load_allowed_labels, load_mappings, load_symptom_map
from core.questioner_llm import propose_questions_llm
from core.voice_transcription import voice_service
from core.clinical_diagnosis import (
    generate_structured_differential_diagnosis,
    analyze_risk_factors,
    generate_red_flag_alerts
)
from core.ehr_integration import create_ehr_integration_summary

# ----------------- App & Logging ------------------
logging.basicConfig(level=os.getenv("LOGLEVEL", "INFO"))
log = logging.getLogger("api")
from dotenv import load_dotenv
load_dotenv()

CXR_CKPT = os.getenv("CXR_CKPT", "checkpoints/biovil_vit_chexpert.pt")
_img_model = ImagingModel(ckpt_path=CXR_CKPT)

if not os.path.exists(CXR_CKPT):
    raise FileNotFoundError(f"CXR checkpoint not found at {CXR_CKPT}. "
                            f"Set CXR_CKPT env var or place the file there.")


app = FastAPI(title="Multimodal Clinical Reference (Advisory)")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------- Environment knobs ----------------
ASK_THRESH = float(os.getenv("ASK_THRESH", "0.70"))         # ask if top_conf < ASK_THRESH
MARGIN_THRESH = float(os.getenv("MARGIN_THRESH", "0.08"))   # or margin between #1 and #2 < MARGIN_THRESH
MAX_CTX_CHARS = int(os.getenv("MAX_CTX_CHARS", "2000"))     # trim retrieved context for faster processing
EHR_JSON = os.getenv("EHR_JSON", "ehr_with_images.json")    # enriched EHR with xray_path/xray_filename

# --------------- Global singletons ----------------
_retriever = get_retriever()
_img_model = ImagingModel(ckpt_path=CXR_CKPT)

# --------------- EHR loading & indices ------------
EHR_RECORDS: List[Dict[str, Any]] = []
EHR_BY_PATIENT: Dict[str, Dict[str, Any]] = {}
EHR_BY_IMAGE: Dict[str, str] = {}  # basename -> patient_id

def _load_ehr() -> None:
    global EHR_RECORDS, EHR_BY_PATIENT, EHR_BY_IMAGE
    EHR_RECORDS, EHR_BY_PATIENT, EHR_BY_IMAGE = [], {}, {}
    try:
        with open(EHR_JSON, "r") as f:
            EHR_RECORDS = json.load(f)
        for r in EHR_RECORDS:
            pid = r.get("patient_id")
            if pid:
                EHR_BY_PATIENT[pid] = r
            xpath = r.get("xray_path")
            if xpath:
                EHR_BY_IMAGE[os.path.basename(xpath)] = pid
        log.info(f"[EHR] Loaded {len(EHR_RECORDS)} records from {EHR_JSON}")
    except FileNotFoundError:
        log.warning(f"[EHR] File not found: {EHR_JSON}. EHR matching will be disabled.")
    except Exception as e:
        log.warning(f"[EHR] Failed to load {EHR_JSON}: {e}")

_load_ehr()

# ----------------- Schemas ------------------------
class InferRequest(BaseModel):
    utterances: List[str]
    patient_id: Optional[str] = None  # optional hint to bind EHR


# ----------------- Helpers ------------------------
def _summarize_ehr(ehr: Optional[Dict[str, Any]]) -> str:
    """Compact, human-readable EHR summary string, safe for context."""
    if not ehr:
        return ""
    parts = []
    pid = ehr.get("patient_id")
    parts.append(f"EHR §patient_id={pid}")
    sex = ehr.get("sex"); age = ehr.get("age")
    if sex or age: parts.append(f"Demographics: {sex or '?'} {age or '?'}y")
    vs = ehr.get("vital_signs") or {}
    if vs:
        kv = []
        for k in ("bp","hr","rr","temp_f","spo2_pct"):
            if k in vs and vs[k] is not None: kv.append(f"{k}={vs[k]}")
        if kv: parts.append("Vitals: " + ", ".join(kv))
    pmh = ehr.get("pmh") or []
    if pmh: parts.append("PMH: " + ", ".join(pmh))
    meds = ehr.get("meds") or []
    if meds: parts.append("Meds: " + ", ".join(meds))
    cxl = ehr.get("chexpert_label")
    if cxl: parts.append(f"CheXpert label (prior): {cxl}")
    note = ehr.get("ehr_notes")
    if note: parts.append("Notes: " + str(note))
    return "\n".join(parts) + "\n\n"

def _scan_text_findings(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive label signals from extracted text using an expanded keyword map.
    Only returns labels that are allowed per domain configuration.
    """
    out: List[Dict[str, Any]] = []
    if not extracted:
        return out

    allowed = set(load_allowed_labels().get("issues_allowed", []))
    maps = load_mappings() or {}
    synonyms_to_issue = {k.strip().lower(): v for k, v in (maps.get("synonyms_to_issue") or {}).items()}

    # Load from JSON config file
    ISSUE_KEYWORDS: Dict[str, List[str]] = load_symptom_map()

    # Build a bag of text from extracted content
    candidate_texts: List[str] = []
    if extracted.get("chief_complaint"):
        candidate_texts.append(str(extracted.get("chief_complaint")))
    candidate_texts.extend([str(s) for s in (extracted.get("symptoms") or [])])
    candidate_texts.extend([str(p) for p in (extracted.get("possible_pmh") or [])])
    candidate_texts.extend([str(m) for m in (extracted.get("possible_meds") or [])])
    haystack = "\n".join(candidate_texts).lower()

    findings: Dict[str, List[str]] = {}

    # 1) Direct keyword search by ISSUE_KEYWORDS
    for issue, keywords in ISSUE_KEYWORDS.items():
        if issue not in allowed:
            continue
        for kw in keywords:
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, haystack):
                findings.setdefault(issue, []).append(kw)

    # 2) Synonym map fallback (mappings.yaml)
    for syn, issue in synonyms_to_issue.items():
        if issue not in allowed:
            continue
        if re.search(r"\b" + re.escape(syn) + r"\b", haystack):
            findings.setdefault(issue, []).append(syn)

    # 3) Vital/BP heuristic
    for s in (extracted.get("symptoms") or []):
        s_low = str(s).lower()
        if "bp" in s_low or re.search(r"\b\d{2,3}/\d{2,3}\b", s_low):
            if "hypertension_uncontrolled" in allowed:
                findings.setdefault("hypertension_uncontrolled", []).append(str(s))

    # Convert to list structure
    for issue, evid in findings.items():
        out.append({"label": issue, "evidence": sorted(list(set(evid)))})
    return out

def _confidence_and_margin(ranked: List[Dict[str, Any]]) -> (float, float):
    if not ranked:
        return 0.0, 0.0
    top = float(ranked[0].get("score", 0.0))
    if len(ranked) < 2:
        return top, top
    second = float(ranked[1].get("score", 0.0))
    return top, max(0.0, top - second)

def _scope_hint(c: float) -> str:
    if c < 0.45: return "broad"
    if c < 0.70: return "mixed"
    return "chest"

# ----------------- Endpoints ----------------------

@app.get("/health")
def health():
    count = get_doc_count()
    return {
        "status": "ok",
        "collection": COLLECTION,
        "persist_dir": PERSIST_DIR,
        "emb_model": EMB_MODEL,
        "top_k": get_top_k(),
        "doc_count": (count if count >= 0 else None),
        "ehr_loaded": len(EHR_RECORDS),
        "voice_transcription": {
            "whisperx_model_loaded": voice_service.whisperx_model is not None,
            "diarization_model_loaded": voice_service.diarize_model is not None,
            "alignment_model_loaded": voice_service.align_model is not None,
        }
    }

@app.post("/infer")
def infer(req: InferRequest):
    """Conversation-only flow (no image)."""
    conversation = "\n".join(req.utterances or [])
    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever.get_relevant_documents(q)
    ctx = render_docs(docs)
    # Add EHR context if patient_id provided
    ehr = EHR_BY_PATIENT.get(req.patient_id) if req.patient_id else None
    ctx = (_summarize_ehr(ehr) if ehr else "") + (ctx[:MAX_CTX_CHARS] if ctx else "")
    answer = answerer_generate(extraction, ctx)
    return {"extraction": extraction, "answer": answer, "ehr": (ehr or None)}

@app.post("/image_infer")
async def image_infer(file: UploadFile = File(...)):
    """Image-only flow, returns image findings."""
    raw = await file.read()
    preds = _img_model.predict(raw)  # expected: [{"label": "...", "score": 0.xx}, ...]
    return {"image_findings": preds, "filename": file.filename}

@app.post("/infer_from_image_only")
async def infer_from_image_only(file: UploadFile = File(...)):
    """
    Image-only flow that tries to bind EHR:
    1) match by filename → EHR
    2) else match by top predicted label → first EHR with same chexpert_label
    """
    raw = await file.read()
    preds = _img_model.predict(raw)
    pid = EHR_BY_IMAGE.get(file.filename)
    ehr = EHR_BY_PATIENT.get(pid) if pid else None

    if ehr is None and preds:
        top = max(preds, key=lambda x: x.get("score", 0.0))
        cxl = top.get("label")
        candidates = [r for r in EHR_RECORDS if r.get("chexpert_label") == cxl]
        ehr = candidates[0] if candidates else None

    return {"image_findings": preds, "ehr": ehr, "filename": file.filename}

@app.post("/structured_diagnosis")
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
    ehr = EHR_BY_PATIENT.get(patient_id) if patient_id else None

    # 1) Extraction
    extraction = extractor_generate(conversation)
    extracted = extraction.get("extracted", {}) or {}

    # 2) Retrieval
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever.get_relevant_documents(q)
    ctx = render_docs(docs)

    # 3) Imaging (optional)
    image_findings: List[Dict[str, Any]] = []
    filename = None
    if file is not None:
        blob = await file.read()
        filename = file.filename
        image_findings = _img_model.predict(blob)
        # Try filename → EHR (takes precedence)
        pid = EHR_BY_IMAGE.get(filename)
        if pid:
            ehr = EHR_BY_PATIENT.get(pid, ehr)

    # 4) Text findings from extraction
    text_findings = _scan_text_findings(extracted)

    # 5) Fusion
    ranked = fuse(image_findings, text_findings, topk=10)
    final = ranked[0] if ranked else None
    domains = bucket_domains([r["condition"] for r in ranked]) if ranked else {}

    # 6) Generate structured differential diagnosis
    structured_diagnosis = generate_structured_differential_diagnosis(
        extraction, ctx, ehr, ranked
    )

    # 7) Generate additional risk analysis
    risk_factors = analyze_risk_factors(extraction, ehr)
    red_flag_alerts = generate_red_flag_alerts(extraction, ehr, ranked)

    # 8) Create EHR integration summary
    ehr_integration = create_ehr_integration_summary(structured_diagnosis, ehr)

    # 9) Live questions (confidence-gated) - simplified to avoid timeout
    top_conf, margin = _confidence_and_margin(ranked)
    questions = []
    # Skip question generation for now to avoid timeout - can be enabled later
    # if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH):
    #     state = {
    #         "top_candidates": ranked[:5],
    #         "image_findings": image_findings,
    #         "ehr_summary": ehr or {},
    #         "text_findings": text_findings,
    #         "extraction": extracted,
    #         "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
    #         "top_confidence": top_conf,
    #         "margin": margin,
    #         "scope_hint": _scope_hint(top_conf),
    #     }
    #     try:
    #         questions = propose_questions_llm(state, max_questions=4)
    #     except Exception as e:
    #         log.warning(f"[coach] question generation failed: {e}")

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
        "structured_diagnosis": structured_diagnosis,
        "risk_analysis": {
            "risk_factors": risk_factors,
            "red_flag_alerts": red_flag_alerts
        },
        "ehr_integration": ehr_integration,
        "coach": {"suggested": questions}
    }

@app.post("/test_structured_diagnosis")
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
    ehr = EHR_BY_PATIENT.get(patient_id) if patient_id else None

    # Simple extraction
    extraction = extractor_generate(conversation)
    
    # Generate structured differential diagnosis with minimal context
    structured_diagnosis = generate_structured_differential_diagnosis(
        extraction, "test context", ehr, []
    )

    return {
        "structured_diagnosis": structured_diagnosis,
        "ehr": ehr,
        "extraction": extraction
    }

@app.post("/multimodal_infer")
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
    ehr = EHR_BY_PATIENT.get(patient_id) if patient_id else None

    # 1) Extraction
    extraction = extractor_generate(conversation)
    extracted = extraction.get("extracted", {}) or {}

    # 2) Retrieval
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever.get_relevant_documents(q)
    ctx = render_docs(docs)

    # 3) Imaging (optional)
    image_findings: List[Dict[str, Any]] = []
    filename = None
    if file is not None:
        blob = await file.read()
        filename = file.filename
        image_findings = _img_model.predict(blob)
        # If payload did NOT provide/resolve an EHR, try filename → EHR
        pid_from_filename = EHR_BY_IMAGE.get(filename)
        if not ehr and pid_from_filename:
            ehr = EHR_BY_PATIENT.get(pid_from_filename, ehr)
        # If payload DID provide EHR and filename maps to a different patient, keep payload's EHR
        elif ehr and pid_from_filename and ehr.get("patient_id") != pid_from_filename:
            log.info(
                f"[EHR] Filename maps to {pid_from_filename} but payload patient_id={ehr.get('patient_id')} provided; keeping payload EHR"
            )

    # 4) Text findings from extraction
    text_findings = _scan_text_findings(extracted)

    # 5) Fusion
    ranked = fuse(image_findings, text_findings, topk=10)
    final = ranked[0] if ranked else None
    domains = bucket_domains([r["condition"] for r in ranked]) if ranked else {}

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
    advisory = answerer_generate(extraction, ctx_full)

    # 8) Live questions (confidence-gated) - simplified to avoid timeout
    top_conf, margin = _confidence_and_margin(ranked)
    questions = []
    # Skip question generation for now to avoid timeout - can be enabled later
    # if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH):
    #     state = {
    #         "top_candidates": ranked[:5],
    #         "image_findings": image_findings,
    #         "ehr_summary": ehr or {},
    #         "text_findings": text_findings,
    #         "extraction": extracted,
    #         "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
    #         "top_confidence": top_conf,
    #         "margin": margin,
    #         "scope_hint": _scope_hint(top_conf),
    #     }
    #     try:
    #         questions = propose_questions_llm(state, max_questions=4)
    #     except Exception as e:
    #         log.warning(f"[coach] question generation failed: {e}")

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
        "rag_advisory": advisory,
        "coach": {"suggested": questions}
    }

@app.post("/voice_transcribe")
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
        
    except Exception as e:
        log.error(f"Error during voice transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Voice transcription failed: {str(e)}")

@app.post("/voice_infer")
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
        ehr = EHR_BY_PATIENT.get(patient_id) if patient_id else None
        
        # 4) Extraction
        extraction = extractor_generate(conversation)
        extracted = extraction.get("extracted", {}) or {}
        
        # 5) Retrieval
        q = extraction.get("retrieval_query") or conversation
        docs = _retriever.get_relevant_documents(q)
        ctx = render_docs(docs)
        
        # 6) Text findings from extraction
        text_findings = _scan_text_findings(extracted)
        
        # 7) Fusion (no image findings for voice-only)
        image_findings: List[Dict[str, Any]] = []
        ranked = fuse(image_findings, text_findings, topk=10)
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
        advisory = answerer_generate(extraction, ctx_full)
        
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
            "rag_advisory": advisory,
            "coach": {"suggested": questions}
        }
        
    except Exception as e:
        log.error(f"Error during voice inference: {e}")
        raise HTTPException(status_code=500, detail=f"Voice inference failed: {str(e)}")

@app.post("/multimodal_voice_infer")
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
        ehr = EHR_BY_PATIENT.get(patient_id) if patient_id else None
        
        # 4) Extraction
        extraction = extractor_generate(conversation)
        extracted = extraction.get("extracted", {}) or {}
        
        # 5) Retrieval
        q = extraction.get("retrieval_query") or conversation
        docs = _retriever.get_relevant_documents(q)
        ctx = render_docs(docs)
        
        # 6) Imaging (optional)
        image_findings: List[Dict[str, Any]] = []
        image_filename = None
        if image_file is not None:
            blob = await image_file.read()
            image_filename = image_file.filename
            image_findings = _img_model.predict(blob)
            # Try filename → EHR (takes precedence)
            pid = EHR_BY_IMAGE.get(image_filename)
            if pid:
                ehr = EHR_BY_PATIENT.get(pid, ehr)
        
        # 7) Text findings from extraction
        text_findings = _scan_text_findings(extracted)
        
        # 8) Fusion
        ranked = fuse(image_findings, text_findings, topk=10)
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
        advisory = answerer_generate(extraction, ctx_full)
        
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
            "rag_advisory": advisory,
            "coach": {"suggested": questions}
        }
        
    except Exception as e:
        log.error(f"Error during multimodal voice inference: {e}")
        raise HTTPException(status_code=500, detail=f"Multimodal voice inference failed: {str(e)}")

# --------------- EHR Integration Endpoints ----------
@app.get("/ehr/patients")
def list_ehr_patients():
    """List all available EHR patients"""
    patients = []
    for record in EHR_RECORDS:
        patients.append({
            "patient_id": record.get("patient_id"),
            "demographics": {
                "age": record.get("age"),
                "sex": record.get("sex")
            },
            "vital_signs": record.get("vital_signs"),
            "pmh": record.get("pmh", []),
            "meds": record.get("meds", []),
            "allergies": record.get("allergies", [])
        })
    return {"patients": patients, "total": len(patients)}

@app.get("/ehr/patients/{patient_id}")
def get_ehr_patient(patient_id: str):
    """Get specific EHR patient data"""
    patient = EHR_BY_PATIENT.get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"patient": patient}

@app.post("/ehr/import_patient_data")
async def import_patient_data(
    patient_id: str = Form(...),
    payload: str = Form(...)
):
    """
    Import patient data from EHR system (mockup for Epic/Cerner integration)
    """
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in payload")
    
    # Mock EHR import - in real implementation, this would connect to Epic/Cerner APIs
    imported_data = {
        "patient_id": patient_id,
        "import_timestamp": datetime.now().isoformat(),
        "source_system": "Epic",  # Could be configurable
        "imported_data": data,
        "status": "imported_successfully"
    }
    
    # In a real implementation, you would:
    # 1. Validate the imported data
    # 2. Store it in your system
    # 3. Update the EHR_BY_PATIENT mapping
    # 4. Return confirmation
    
    return {
        "message": "Patient data imported successfully (mockup)",
        "import_details": imported_data
    }

@app.post("/ehr/export_clinical_summary")
async def export_clinical_summary(
    patient_id: str = Form(...),
    diagnosis_result: str = Form(...)
):
    """
    Export clinical summary back to EHR system (mockup for Epic/Cerner integration)
    """
    try:
        diagnosis_data = json.loads(diagnosis_result)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in diagnosis_result")
    
    # Mock EHR export - in real implementation, this would send data to Epic/Cerner
    export_data = {
        "patient_id": patient_id,
        "export_timestamp": datetime.now().isoformat(),
        "target_system": "Epic",
        "clinical_summary": diagnosis_data,
        "status": "exported_successfully"
    }
    
    # In a real implementation, you would:
    # 1. Format the data according to EHR standards (HL7 FHIR, etc.)
    # 2. Send via API to the EHR system
    # 3. Handle authentication and authorization
    # 4. Return confirmation
    
    return {
        "message": "Clinical summary exported successfully (mockup)",
        "export_details": export_data
    }

# --------------- Knowledge Base Management ----------
@app.get("/knowledge_base/mode")
def get_knowledge_base_mode():
    """Get current knowledge base mode"""
    return {
        "mode": "clinical",
        "sources": ["Clinical Guidelines", "UpToDate", "PubMed"],
        "last_updated": "2024-01-01T00:00:00Z"
    }

@app.post("/knowledge_base/mode")
def set_knowledge_base_mode(mode: str = Form(...)):
    """Set knowledge base mode"""
    return {
        "mode": mode,
        "sources": ["Clinical Guidelines", "UpToDate", "PubMed"],
        "last_updated": datetime.now().isoformat()
    }

# --------------- Optional: hot-reload EHR ----------
@app.post("/reload_ehr")
def reload_ehr():
    """Reload EHR JSON without restarting the server (optional convenience)."""
    _load_ehr()
    return {"ehr_loaded": len(EHR_RECORDS), "ehr_source": EHR_JSON}

# Tip:
#   uvicorn server:app --host 0.0.0.0 --port 8000
# Env:
#   export EHR_JSON="ehr_with_images.json"
#   export RAG_PERSIST_DIR=./rag_store
#   export RAG_COLLECTION=conversations
#   export RAG_EMB_MODEL=sentence-transformers/all-mpnet-base-v2
#   export GROQ_API_KEY=...
#   export GROQ_MODEL=llama-3.1-70b-versatile
#   export ASK_THRESH=0.70
#   export MARGIN_THRESH=0.08

