# server.py
import os
import re
import json
import logging
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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

# --------------- Environment knobs ----------------
ASK_THRESH = float(os.getenv("ASK_THRESH", "0.70"))         # ask if top_conf < ASK_THRESH
MARGIN_THRESH = float(os.getenv("MARGIN_THRESH", "0.08"))   # or margin between #1 and #2 < MARGIN_THRESH
MAX_CTX_CHARS = int(os.getenv("MAX_CTX_CHARS", "4000"))     # trim retrieved context
EHR_JSON = os.getenv("EHR_JSON", "ehr_with_images.json")    # enriched EHR with xray_path/xray_filename

# --------------- Global singletons ----------------
_retriever = get_retriever()
_img_model = ImagingModel("checkpoints/biovil_vit_chexpert.pt")

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

    # 8) Live questions (confidence-gated)
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

