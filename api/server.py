import json
import re
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

from core.extract import extractor_generate
from core.answer import answerer_generate
from core.retriever import get_retriever, render_docs, get_doc_count, get_top_k, PERSIST_DIR, COLLECTION, EMB_MODEL
from core.imaging import ImagingModel
from core.fusion import fuse
from core.domains import bucket_domains

app = FastAPI(title="Multimodal Clinical Decision Support")
_retriever = get_retriever()
_img_model = ImagingModel()

class InferRequest(BaseModel):
    utterances: List[str]

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
    }

@app.post("/infer")
def infer(req: InferRequest):
    conversation = "\n".join(req.utterances)
    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever.get_relevant_documents(q)
    ctx = render_docs(docs)
    answer = answerer_generate(extraction, ctx)
    return {"extraction": extraction, "answer": answer}

@app.post("/image_infer")
async def image_infer(file: UploadFile = File(...)):
    bytes_ = await file.read()
    preds = _img_model.predict(bytes_)
    return {"image_findings": preds}

@app.post("/multimodal_infer")
async def multimodal_infer(payload: str = Form(...), file: UploadFile = File(None)):
    data = json.loads(payload)
    utterances = data.get("utterances", [])
    conversation = "\n".join(utterances)

    extraction = extractor_generate(conversation)
    q = extraction.get("retrieval_query") or conversation
    docs = _retriever.get_relevant_documents(q)
    ctx = render_docs(docs)

    image_findings: List[Dict[str, Any]] = []
    if file is not None:
        bytes_ = await file.read()
        image_findings = _img_model.predict(bytes_)

    text_findings: List[Dict[str, Any]] = []
    extracted = extraction.get("extracted", {}) or {}
    for s in extracted.get("symptoms", []):
        s_low = s.lower()
        if "bp" in s_low or re.search(r"\b\d{2,3}/\d{2,3}\b", s_low):
            text_findings.append({"label": "hypertension_uncontrolled", "evidence": [s]})
    for pmh in extracted.get("possible_pmh", []) or []:
        text_findings.append({"label": pmh.lower().replace(" ", "_"), "evidence": [pmh]})

    ranked = fuse(image_findings, text_findings, topk=10)
    final = ranked[0] if ranked else None
    domains = bucket_domains([r["condition"] for r in ranked])

    fused_header = ""
    if ranked:
        fused_header = "Source=FUSED §Top candidates\n" + "\n".join([
            f"{i+1}. {r['condition']} ({r['score']:.2f}) – {r['why']}" for i, r in enumerate(ranked)
        ]) + "\n\n"

    advisory = answerer_generate(extraction, fused_header + ctx)

    return {
        "image_findings": image_findings,
        "text_findings": text_findings,
        "domains": domains,
        "fusion": {"top10": ranked, "final_suggested_issue": final},
        "rag_advisory": advisory,
    }

# Tip: uvicorn api.server:app --host 0.0.0.0 --port 8000


