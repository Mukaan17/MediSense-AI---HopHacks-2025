# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 15:49:29
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:58:04
# server.py
import os
import re
import json
import hashlib
import logging
import threading
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---- Core components (you already have these) ----
from core.extract import extractor_generate
from core.answer import answerer_generate
from core.retriever import (
    get_retriever, render_docs, get_doc_count, get_top_k,
    warm_up as retriever_warm_up, reset as retriever_reset,
    PERSIST_DIR, COLLECTION, EMB_MODEL
)
try:
    from core.imaging import ImagingModel
    _IMAGING_IMPORT_ERROR = None
except Exception as _img_import_exc:  # pragma: no cover - optional dependency fallback
    ImagingModel = None
    _IMAGING_IMPORT_ERROR = str(_img_import_exc)
from core.fusion import fuse
from core.evidence_engine import build_evidence
from core.domains import bucket_domains
import uuid
from core.config import load_allowed_labels, load_mappings, load_symptom_map
from core.questioner_llm import (
    propose_questions_llm,
    stream_live_suggestions,
    parse_bullet_questions,
)
from core.llm_client import (
    anthropic_available,
    invoke_claude_full,
    get_llm,
    get_final_model,
    get_fallback_final_model,
)
from core.summarize import summarize_live
from core.diagnostic_suggestions import generate_diagnostic_suggestions
from core.voice_transcription import voice_service
from core.clinical_diagnosis import (
    generate_structured_differential_diagnosis,
    analyze_risk_factors,
    generate_red_flag_alerts,
    generate_brief_diagnosis_summary,
)
from core.ehr_integration import create_ehr_integration_summary
from core.app_mode import APP_MODE, is_demo, is_clinical, ehr_is_synthetic
from core.auth import (
    DEMO_USER, PUBLIC_PATHS, TOKEN_TTL_MINUTES,
    authenticate, create_access_token, user_from_authorization, user_from_ws_token,
)
from core.audit import audit_event, new_request_id
from fastapi.responses import JSONResponse
import time

# ----------------- App & Logging ------------------
logging.basicConfig(level=os.getenv("LOGLEVEL", "INFO"))
log = logging.getLogger("api")
from dotenv import load_dotenv
load_dotenv()

CXR_CKPT = os.getenv("CXR_CKPT", "checkpoints/biovil_vit_chexpert.pt")
_img_model: Optional[ImagingModel] = None
if ImagingModel is None:
    log.warning(f"[IMG] Imaging dependencies unavailable: {_IMAGING_IMPORT_ERROR}")
elif os.path.exists(CXR_CKPT):
    try:
        _img_model = ImagingModel(ckpt_path=CXR_CKPT)
    except Exception as e:
        log.warning(f"[IMG] Failed to initialize imaging model from {CXR_CKPT}: {e}")
else:
    log.warning(
        f"[IMG] Checkpoint not found at {CXR_CKPT}. "
        "Image endpoints will be unavailable until CXR_CKPT is configured."
    )


app = FastAPI(title="Multimodal Clinical Reference (Advisory)")


# --------------- Security middleware ----------------
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
_rate_buckets: Dict[str, List[float]] = {}
_rate_lock = threading.Lock()


@app.middleware("http")
async def _security_middleware(request, call_next):
    request_id = new_request_id()
    start = time.perf_counter()
    path = request.url.path
    client = request.client.host if request.client else "unknown"

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse({"detail": f"Request too large (> {MAX_UPLOAD_MB} MB)"}, status_code=413)

    if RATE_LIMIT_PER_MINUTE > 0 and path != "/health":
        now = time.monotonic()
        with _rate_lock:
            bucket = _rate_buckets.setdefault(client, [])
            cutoff = now - 60.0
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= RATE_LIMIT_PER_MINUTE:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
            bucket.append(now)

    user = DEMO_USER
    if path not in PUBLIC_PATHS and not path.startswith(("/docs", "/openapi")):
        try:
            user = user_from_authorization(request.headers.get("authorization"))
        except HTTPException as e:
            audit_event("auth_denied", request_id=request_id, method=request.method,
                        path=path, status=e.status_code, detail=str(e.detail))
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    request.state.user = user
    request.state.request_id = request_id

    response = await call_next(request)

    # Audit: identifiers and outcomes only - never clinical content.
    audit_event("request", request_id=request_id, user=user.get("username", ""),
                method=request.method, path=path, status=response.status_code,
                patient_id=request.query_params.get("patient_id"),
                duration_ms=(time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    return response


@app.post("/auth/login")
def auth_login(username: str = Form(...), password: str = Form(...)):
    """Exchange credentials for a bearer token (required in clinical mode)."""
    user = authenticate(username, password)
    if not user:
        audit_event("login_failed", user=username, path="/auth/login", status=401)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user["username"], user["role"])
    audit_event("login", user=username, path="/auth/login", status=200)
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "expires_in_minutes": TOKEN_TTL_MINUTES}


@app.on_event("startup")
async def _warm_up_models() -> None:
    # Load the vector store and cross-encoder off the request path so the
    # first live query doesn't pay model-load (or download) latency.
    threading.Thread(target=retriever_warm_up, daemon=True).start()

# Add CORS middleware (configurable via FRONTEND_ORIGINS env var)
origins_env = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS = [o.strip() for o in origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --------------- Environment knobs ----------------
ASK_THRESH = float(os.getenv("ASK_THRESH", "0.70"))         # ask if top_conf < ASK_THRESH
MARGIN_THRESH = float(os.getenv("MARGIN_THRESH", "0.08"))   # or margin between #1 and #2 < MARGIN_THRESH
MAX_CTX_CHARS = int(os.getenv("MAX_CTX_CHARS", "2000"))     # trim retrieved context for faster processing
EHR_JSON = os.getenv("EHR_JSON", "ehr_with_images.json")    # enriched EHR with xray_path/xray_filename

# --------------- Global singletons ----------------
_retriever = None


def _retriever_instance():
    global _retriever
    if _retriever is None:
        _retriever = get_retriever()
    return _retriever

# --------------- EHR loading & indices ------------
EHR_RECORDS: List[Dict[str, Any]] = []
EHR_BY_PATIENT: Dict[str, Dict[str, Any]] = {}
EHR_BY_IMAGE_PATH: Dict[str, str] = {}          # normalized xray_path -> patient_id
EHR_BY_IMAGE_BASENAME: Dict[str, List[str]] = {}  # basename -> [patient_id...]
EHR_BY_IMAGE_HASH: Dict[str, str] = {}          # sha256(image bytes) -> patient_id


def _normalize_image_relpath(path: Optional[str]) -> str:
    if not path:
        return ""
    p = str(path).strip().replace("\\", "/")
    p = re.sub(r"^(\./)+", "", p)
    prefix = "CheXpert-v1.0-small/"
    if p.startswith(prefix):
        p = p[len(prefix):]
    if p.startswith("chexpert/"):
        p = p[len("chexpert/"):]
    return p.lstrip("/")


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _candidate_local_image_paths(rel_or_abs_path: str) -> List[str]:
    normalized = _normalize_image_relpath(rel_or_abs_path)
    candidates = [rel_or_abs_path, normalized, os.path.join("chexpert", normalized)]
    out = []
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _append_basename_index(path_like: Optional[str], patient_id: str) -> None:
    if not path_like:
        return
    base = os.path.basename(_normalize_image_relpath(path_like))
    if not base:
        return
    EHR_BY_IMAGE_BASENAME.setdefault(base, [])
    if patient_id not in EHR_BY_IMAGE_BASENAME[base]:
        EHR_BY_IMAGE_BASENAME[base].append(patient_id)


def _ehr_fallback_by_top_label(preds: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not preds:
        return None
    top = max(preds, key=lambda x: x.get("score", x.get("prob", 0.0)))
    cxl = top.get("label")
    if not cxl:
        return None
    candidates = [r for r in EHR_RECORDS if r.get("chexpert_label") == cxl]
    return candidates[0] if candidates else None


def _resolve_ehr_from_uploaded_image(
    raw_bytes: Optional[bytes],
    filename: Optional[str],
    preds: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    # 1) Content hash match (most reliable; handles basename collisions)
    if raw_bytes:
        img_hash = _sha256_bytes(raw_bytes)
        pid = EHR_BY_IMAGE_HASH.get(img_hash)
        if pid:
            return EHR_BY_PATIENT.get(pid)

    # 2) Exact path match if client sends a relative path
    norm_name = _normalize_image_relpath(filename)
    if norm_name:
        pid = EHR_BY_IMAGE_PATH.get(norm_name)
        if pid:
            return EHR_BY_PATIENT.get(pid)

    # 3) Basename candidates; disambiguate by top predicted label when available
    base = os.path.basename(norm_name) if norm_name else ""
    if base:
        pids = EHR_BY_IMAGE_BASENAME.get(base, [])
        if len(pids) == 1:
            return EHR_BY_PATIENT.get(pids[0])
        if len(pids) > 1:
            candidates = [EHR_BY_PATIENT.get(pid) for pid in pids if pid in EHR_BY_PATIENT]
            candidates = [c for c in candidates if c]
            if preds:
                top = max(preds, key=lambda x: x.get("score", x.get("prob", 0.0)))
                top_label = top.get("label")
                by_label = [c for c in candidates if c.get("chexpert_label") == top_label]
                if by_label:
                    return by_label[0]
            return candidates[0] if candidates else None

    # 4) Label fallback
    return _ehr_fallback_by_top_label(preds)




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


def _gated_questions(ranked: List[Dict[str, Any]], top_conf: float, margin: float,
                     image_findings: List[Dict[str, Any]], ehr: Optional[Dict[str, Any]],
                     text_findings: List[Dict[str, Any]], extracted: Dict[str, Any],
                     ctx: str, max_questions: int = 3) -> List[Dict[str, Any]]:
    """Confidence-gated clarifying questions, shared by the batch endpoints.
    Failures degrade to an empty list; never blocks a response."""
    if not ((top_conf < ASK_THRESH) or (margin < MARGIN_THRESH and top_conf < 0.95)):
        return []
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
        return propose_questions_llm(state, max_questions=max_questions)
    except Exception as e:
        log.warning(f"[coach] question generation failed: {e}")
        return []


def _predict_image_with_fallback(raw_bytes: bytes, filename: Optional[str]) -> List[Dict[str, Any]]:
    # Primary path: model inference.
    if _img_model is not None:
        return _img_model.predict(raw_bytes)

    # Offline fallback: if the uploaded image can be linked to an EHR row, use
    # its recorded label. The score is a fixed placeholder, not model output -
    # flag it so downstream consumers and the UI can say so.
    linked_ehr = _resolve_ehr_from_uploaded_image(raw_bytes, filename, preds=None)
    fallback_label = linked_ehr.get("chexpert_label") if linked_ehr else None
    if fallback_label:
        return [{
            "label": fallback_label,
            "score": 0.60,
            "source": "ehr_linked_label_fallback",
            "fallback": True,
            "note": "Imaging model unavailable; label taken from the linked EHR record, score is a placeholder.",
        }]

    raise HTTPException(
        status_code=503,
        detail="Imaging model unavailable and no EHR-linked fallback label could be resolved for this image."
    )

def _load_ehr() -> None:
    global EHR_RECORDS, EHR_BY_PATIENT, EHR_BY_IMAGE_PATH, EHR_BY_IMAGE_BASENAME, EHR_BY_IMAGE_HASH
    EHR_RECORDS, EHR_BY_PATIENT = [], {}
    EHR_BY_IMAGE_PATH, EHR_BY_IMAGE_BASENAME, EHR_BY_IMAGE_HASH = {}, {}, {}
    try:
        with open(EHR_JSON, "r") as f:
            EHR_RECORDS = json.load(f)
        for r in EHR_RECORDS:
            pid = r.get("patient_id")
            if pid:
                EHR_BY_PATIENT[pid] = r
            xpath = r.get("xray_path")
            if xpath:
                norm_xpath = _normalize_image_relpath(xpath)
                r["xray_path"] = norm_xpath
                if norm_xpath and pid:
                    EHR_BY_IMAGE_PATH[norm_xpath] = pid
                    _append_basename_index(norm_xpath, pid)
            if pid:
                _append_basename_index(r.get("xray_filename"), pid)

            # Build a content-hash index for robust matching even when basenames collide.
            if pid and xpath:
                for local_path in _candidate_local_image_paths(xpath):
                    if not os.path.exists(local_path):
                        continue
                    # Hashing every linked image couples startup time to
                    # dataset size; default is skip (set SKIP_HASH=0 to
                    # enable content-hash EHR matching with local images).
                    if os.getenv("SKIP_HASH", "1").strip().lower() not in ("0", "false", "no"):
                        continue
                    digest = _sha256_file(local_path)
                    if not digest:
                        continue
                    EHR_BY_IMAGE_HASH[digest] = pid
                    break
        log.info(f"[EHR] Loaded {len(EHR_RECORDS)} records from {EHR_JSON}")
        log.info(
            f"[EHR] Indexed path={len(EHR_BY_IMAGE_PATH)} "
            f"basename={len(EHR_BY_IMAGE_BASENAME)} hash={len(EHR_BY_IMAGE_HASH)}"
        )
    except FileNotFoundError:
        log.warning(f"[EHR] File not found: {EHR_JSON}. EHR matching will be disabled.")
    except Exception as e:
        log.warning(f"[EHR] Failed to load {EHR_JSON}: {e}")

_load_ehr()

# --- CheXpert -> domain ontology aliases (extend as needed) ---
ALIASES = {
    "Pleural Effusion": "pleural_effusion_suspected",
    "Atelectasis": "atelectasis",
    "Consolidation": "pneumonia_unspecified",
    "Enlarged Cardiomediastinum": "cardiomegaly",
    "Lung Lesion": "lung_lesion_suspected",
    "Pleural Other": "pleural_other_suspected",
}

# --- live-case store: Redis when REDIS_URL is set (shared across
# workers/tasks, TTL-expired), else per-process memory with TTL + cap ---
from core.case_store import make_case_store
_case_store = make_case_store()

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

    # 4) Trauma/infectious heuristics from deterministic extractor cues.
    trauma_cues = [str(x).lower() for x in (extracted.get("trauma_cues") or [])]
    infectious_cues = [str(x).lower() for x in (extracted.get("infectious_cues") or [])]

    if trauma_cues:
        if "musculoskeletal_chest_pain" in allowed:
            findings.setdefault("musculoskeletal_chest_pain", []).extend(trauma_cues)
        if "pneumothorax_red_flags" in allowed:
            if any(t in haystack for t in ["shortness of breath", "dyspnea", "chest pain", "pleuritic"]):
                findings.setdefault("pneumothorax_red_flags", []).extend(trauma_cues)

    if infectious_cues:
        if "pneumonia_unspecified" in allowed:
            findings.setdefault("pneumonia_unspecified", []).extend(infectious_cues)
        if "upper_respiratory_infection" in allowed and any(t in haystack for t in ["sore throat", "congestion", "runny nose"]):
            findings.setdefault("upper_respiratory_infection", []).extend(infectious_cues)

    # 5) Combined cue heuristic: fever + cough strongly supports infection.
    if ("fever" in haystack and "cough" in haystack) and "pneumonia_unspecified" in allowed:
        findings.setdefault("pneumonia_unspecified", []).append("fever+cough")

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

def _quick_facts(ehr: Optional[Dict[str, Any]]) -> Optional[str]:
    if not ehr: return None
    vs = ehr.get("vital_signs", {})
    return f"{ehr.get('sex','?')} {ehr.get('age','?')} | SpO2 {vs.get('spo2_pct','?')}% | HR {vs.get('hr','?')} | BP {vs.get('bp','?')}"

def _pick_question(questions: List[Dict[str, Any]]) -> Optional[str]:
    if not questions: return None
    red = [q for q in questions if q.get("priority") == "red-flag"]
    return (red[0] if red else questions[0]).get("q")


def _derive_summary(
    advisory: Optional[Dict[str, Any]] = None,
    ranked: Optional[List[Dict[str, Any]]] = None
) -> str:
    if isinstance(advisory, dict):
        follow_up = advisory.get("follow_up")
        if follow_up:
            return str(follow_up)
        ranked_issues = advisory.get("potential_issues_ranked") or []
        if ranked_issues:
            top = ranked_issues[0]
            cond = top.get("condition")
            conf = top.get("confidence")
            if cond is not None and conf is not None:
                return f"Top advisory issue: {cond} (confidence {float(conf):.2f})."
    if ranked:
        top = ranked[0]
        return f"Top multimodal candidate: {top.get('condition')} ({float(top.get('score', 0.0)):.2f})."
    return "Clinical analysis completed."

def _compact_live(
    ranked: List[Dict[str, Any]],
    top_conf: float,
    margin: float,
    ehr: Optional[Dict[str, Any]],
    questions: List[Dict[str, Any]],
    max_candidates: int,
    min_conf: float,
    diagnostic_suggestions: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    dx = ranked[0]["condition"] if ranked else None
    alts = []
    for r in ranked[1:]:
        if len(alts) >= (max_candidates - 1): break
        if r.get("score", 0.0) >= min_conf:
            alts.append(f"{r['condition']} {r['score']:.2f}")
    
    result = {
        "dx": dx,
        "conf": round(float(top_conf or 0.0), 2),
        "quick_facts": _quick_facts(ehr),
        "why": "combined image+EHR" if ranked else None,
        "next_question": _pick_question(questions),
        "alts": alts,
        "alerts": {"red_flag": bool(questions and questions[0].get("priority") == "red-flag"),
                   "margin": round(float(margin or 0.0), 2)}
    }
    
    # Add enhanced diagnostic suggestions if available
    if diagnostic_suggestions:
        result.update(diagnostic_suggestions)
    
    return result

# ----------------- Endpoints ----------------------

@app.get("/health")
def health():
    count = get_doc_count()
    return {
        "status": "ok",
        "app_mode": APP_MODE,
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

@app.post("/infer")
def infer(req: InferRequest):
    """Conversation-only flow (no image)."""
    conversation = "\n".join(req.utterances or [])
    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever_instance().get_relevant_documents(q)
    ctx = render_docs(docs)
    # Add EHR context if patient_id provided
    ehr = EHR_BY_PATIENT.get(req.patient_id) if req.patient_id else None
    ctx = (_summarize_ehr(ehr) if ehr else "") + (ctx[:MAX_CTX_CHARS] if ctx else "")
    answer = _call_llm(answerer_generate, extraction, ctx)
    return {
        "extraction": extraction,
        "answer": answer,
        "ehr": (ehr or None),
        "summary": _derive_summary(advisory=answer),
    }

@app.post("/image_infer")
async def image_infer(file: UploadFile = File(...)):
    """Image-only flow, returns image findings."""
    raw = await file.read()
    preds = _predict_image_with_fallback(raw, file.filename)
    return {"image_findings": preds, "filename": file.filename}

@app.post("/quick_analysis")
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

@app.post("/infer_from_image_only")
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
    structured_diagnosis = _call_llm(generate_structured_differential_diagnosis, 
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
    except HTTPException:
        raise
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

# --------------- EHR Integration Endpoints ----------
@app.get("/ehr/patients")
def list_ehr_patients():
    """List all available EHR patients"""
    _guard_synthetic_ehr()
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
    return {"patients": patients, "total": len(patients),
            "data_source": ("synthetic_demo" if ehr_is_synthetic(EHR_JSON) else "configured")}

@app.get("/ehr/patients/{patient_id}")
def get_ehr_patient(patient_id: str):
    """Get specific EHR patient data"""
    _guard_synthetic_ehr()
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
    _demo_only("EHR import")
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
    _demo_only("Clinical summary export")
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
    _demo_only("Knowledge base mode toggle")
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

@app.post("/reload_retriever")
def reload_retriever():
    """Re-initialize the RAG store after a KB rebuild (init is otherwise
    once-per-process). Re-warms on a background thread."""
    global _retriever
    count_before = get_doc_count()
    retriever_reset()
    _retriever = None
    threading.Thread(target=retriever_warm_up, daemon=True).start()
    return {"status": "reloading", "doc_count_before": count_before}

# Tip:
#   uvicorn api.server:app --host 0.0.0.0 --port 8000
# Env:
#   export EHR_JSON="ehr_with_images.json"
#   export RAG_PERSIST_DIR=./rag_store
#   export RAG_COLLECTION=conversations
#   export RAG_EMB_MODEL=sentence-transformers/all-MiniLM-L6-v2
#   export GEMINI_API_KEY=...
#   export GEMINI_MODEL=gemini-2.5-flash-lite
#   export ASK_THRESH=0.70
#   export MARGIN_THRESH=0.08

# --------------- Live Case Management ----------

@app.post("/api/case/voice")
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

@app.post("/api/case")
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

class TranscribeIn(BaseModel):
    utterance: str

@app.post("/api/case/{case_id}/transcribe")
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

# ----------------- Live-case recompute (shared by WS + finalize) ----------------------

def _recompute_case(case: Dict[str, Any],
                    latest_utterance: Optional[str] = None,
                    latest_speaker: Optional[str] = None):
    """Run the full per-utterance pipeline synchronously.

    Returns (hud, question_state, details): hud is the HUD payload without
    coach questions (attached by the caller after generation), question_state
    is the coach input dict when the confidence gate passes (else None), and
    details carries the ranked list + retrieved context for the finalize
    report. Runs in a worker thread via asyncio.to_thread so it never blocks
    the event loop.
    """
    utterances = case.get("utterances", [])
    conversation = "\n".join(utterances)

    extraction = extractor_generate(conversation) if conversation else {"extracted": {}}
    q = (extraction.get("retrieval_query") or conversation) if conversation else ""
    docs = _retriever_instance().get_relevant_documents(q) if q else []
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
    top_conf, margin = _confidence_and_margin(ranked)

    question_state = None
    if (top_conf < ASK_THRESH) or (margin < MARGIN_THRESH and top_conf < 0.95):
        question_state = {
            "top_candidates": ranked[:5],
            "image_findings": case["image_findings"],
            "ehr_summary": case["ehr"] or {},
            "text_findings": text_findings,
            "extraction": extracted,
            "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
            "top_confidence": top_conf,
            "margin": margin,
            "scope_hint": _scope_hint(top_conf),
        }

    diagnostic_suggestions = None
    try:
        diagnostic_suggestions = generate_diagnostic_suggestions({
            "top_candidates": ranked[:5],
            "image_findings": case["image_findings"],
            "ehr_summary": case["ehr"] or {},
            "text_findings": text_findings,
            "extraction": extracted,
            "retrieved_context": (ctx or "")[:MAX_CTX_CHARS],
            "top_confidence": top_conf,
            "margin": margin,
        }, max_suggestions=4)
    except Exception as e:
        log.warning(f"[coach] diagnostic suggestions generation failed: {e}")

    summary = summarize_live(utterances, max_words=40) if utterances else ""
    hud = _compact_live(ranked, top_conf, margin, case["ehr"], [], max_candidates=3,
                        min_conf=0.6, diagnostic_suggestions=diagnostic_suggestions)
    hud["evidence"] = evidence
    hud["summary"] = summary
    if latest_utterance:
        hud["transcript_chunk"] = {"speaker": (latest_speaker or "unknown"), "text": latest_utterance}

    details = {"ranked": ranked, "ctx": ctx, "extraction": extracted,
               "top_conf": top_conf, "margin": margin}
    return hud, question_state, details


def _apply_questions(hud: Dict[str, Any], questions: List[Dict[str, Any]]) -> None:
    hud["next_question"] = _pick_question(questions)
    hud["coach"] = {"suggested": questions}
    alerts = hud.get("alerts") or {}
    alerts["red_flag"] = bool(questions and questions[0].get("priority") == "red-flag")
    hud["alerts"] = alerts


# ----------------- Final case report ----------------------

FINAL_REPORT_SYSTEM = (
    "You are a cautious clinical reference assistant producing an advisory "
    "case summary for a clinician. You do NOT diagnose or prescribe. Frame "
    "findings as advisory considerations to correlate clinically, cite the "
    "provided reference context where used, and use ONLY the information "
    "provided."
)


def _final_report_prompt(conversation: str, ehr_ctx: str, ranked: List[Dict[str, Any]],
                         ctx: str) -> str:
    ranked_lines = "\n".join(
        f"{i + 1}. {r.get('condition')} (score {r.get('score', 0.0):.2f})"
        for i, r in enumerate(ranked[:10])
    ) or "(none)"
    allowed = ", ".join(sorted(load_allowed_labels()))
    return (
        "CONVERSATION TRANSCRIPT (speaker-prefixed lines):\n"
        f"{conversation}\n\n"
        f"PATIENT CONTEXT (EHR):\n{ehr_ctx or '(none)'}\n\n"
        f"MODEL-FUSED CANDIDATE CONDITIONS (advisory signals, not diagnoses):\n{ranked_lines}\n\n"
        f"RETRIEVED REFERENCE CONTEXT:\n{(ctx or '(none)')[:MAX_CTX_CHARS]}\n\n"
        "Write a structured advisory case report with sections:\n"
        "1. Case summary (2-4 sentences)\n"
        "2. Leading considerations - up to 3, each with supporting evidence "
        "from the transcript/EHR/imaging and what would help rule it in or out\n"
        "3. Red flags to screen\n"
        "4. Suggested next steps (non-prescriptive: assessments, correlations, "
        "escalation criteria - never medications or doses)\n"
        "5. Citations of the reference context used\n\n"
        f"Condition names must come from this closed vocabulary: {allowed}"
    )


@app.post("/api/case/{case_id}/finalize")
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


# ----------------- WebSocket live speech-to-text ----------------------

@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    """Raw 16 kHz mono Int16 PCM frames in (binary), utterance transcripts
    out (JSON). A text frame {"event": "flush"} force-closes the current
    utterance (sent by the client on Stop Recording)."""
    from core.live_stt import UtteranceBuffer, transcribe_pcm, stt_executor, fw_available

    await ws.accept()
    if user_from_ws_token(ws.query_params.get("token")) is None:
        await ws.close(code=4401, reason="Authentication required")
        return
    if not await asyncio.get_running_loop().run_in_executor(stt_executor, fw_available):
        await ws.send_json({"error": "server-side transcription unavailable"})
        await ws.close()
        return

    buffer = UtteranceBuffer()
    loop = asyncio.get_running_loop()

    async def _emit(pcm: Optional[bytes]) -> None:
        if not pcm:
            return
        text = await loop.run_in_executor(stt_executor, transcribe_pcm, pcm)
        if text:
            await ws.send_json({"transcript": text, "final": True})

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data:
                await _emit(buffer.add(data))
                continue
            text = message.get("text")
            if text:
                try:
                    event = json.loads(text)
                except Exception:
                    continue
                if event.get("event") == "flush":
                    await _emit(buffer.flush())
    except WebSocketDisconnect:
        return
    except Exception as e:
        log.warning(f"[STT] transcribe socket error: {e}")
        try:
            await ws.close()
        except Exception:
            pass


# ----------------- WebSocket Live Transcribing ----------------------

@app.websocket("/ws/case/{case_id}")
async def ws_case(ws: WebSocket, case_id: str):
    await ws.accept()
    if user_from_ws_token(ws.query_params.get("token")) is None:
        await ws.close(code=4401, reason="Authentication required")
        return
    case = _case_store.get(case_id)
    if case is None:
        await ws.send_json({"error": "case_id not found"})
        await ws.close()
        return

    async def _send_update(latest_utterance: Optional[str] = None,
                           latest_speaker: Optional[str] = None):
        # Heavy pipeline runs in a worker thread; the event loop stays free
        # for other connections.
        hud, question_state, _ = await asyncio.to_thread(
            _recompute_case, case, latest_utterance, latest_speaker)

        if question_state is not None:
            questions: List[Dict[str, Any]] = []
            if anthropic_available():
                try:
                    parts: List[str] = []
                    async for token in stream_live_suggestions(question_state):
                        parts.append(token)
                        await ws.send_json({"type": "streaming_token", "token": token})
                    questions = parse_bullet_questions("".join(parts), max_questions=3)
                except Exception as e:
                    log.warning(f"[coach] Claude streaming failed, falling back: {e}")
            if not questions:
                try:
                    questions = await asyncio.to_thread(propose_questions_llm, question_state, 3)
                except Exception as e:
                    log.warning(f"[coach] question generation failed: {e}")
            _apply_questions(hud, questions)

        await ws.send_json(hud)

    await _send_update()

    try:
        while True:
            msg = await ws.receive_json()
            batch = [msg]
            # Collapse bursts: drain messages that arrived while the previous
            # recompute ran, so a fast talker triggers one recompute per burst
            # instead of one full pipeline per utterance.
            while True:
                try:
                    batch.append(await asyncio.wait_for(ws.receive_json(), timeout=0.05))
                except asyncio.TimeoutError:
                    break

            latest_utt, latest_speaker = None, None
            for m in batch:
                utt = m.get("utterance")
                speaker = m.get("speaker")
                if isinstance(utt, str) and utt.strip():
                    prefixed = f"{speaker}: {utt.strip()}" if speaker in ("patient", "doctor") else utt.strip()
                    case.setdefault("utterances", []).append(prefixed)
                    latest_utt, latest_speaker = utt.strip(), speaker
            if latest_utt is not None:
                _case_store.put(case_id, case)
                await _send_update(latest_utterance=latest_utt, latest_speaker=latest_speaker)
    except WebSocketDisconnect:
        return
    except Exception as e:
        await ws.send_json({"error": str(e)})
        await ws.close()
