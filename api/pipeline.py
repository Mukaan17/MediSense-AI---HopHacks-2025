# -*- coding: utf-8 -*-
"""The shared inference pipeline: text findings, fusion + evidence
recompute, HUD assembly, gated coach questions, and the final-report
prompt. Route modules stay thin by composing these."""

import re
import logging
from typing import List, Dict, Any, Optional


from core.extract import extractor_generate
from core.retriever import (
    render_docs,
)
from core.fusion import fuse
from core.evidence_engine import build_evidence
from core.config import load_allowed_labels, load_mappings, load_symptom_map
from core.questioner_llm import (
    propose_questions_llm,
)
from core.summarize import summarize_live
from core.diagnostic_suggestions import generate_diagnostic_suggestions
from core import metrics

log = logging.getLogger("api")

from api.settings import (
    ASK_THRESH,
    MARGIN_THRESH,
    MAX_CTX_CHARS,
)
from api.state import (
    _retriever_instance,
)

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

    with metrics.timed("stage_latency", stage="extract"):
        extraction = extractor_generate(conversation) if conversation else {"extracted": {}}
    q = (extraction.get("retrieval_query") or conversation) if conversation else ""
    with metrics.timed("stage_latency", stage="retrieve"):
        docs = _retriever_instance().get_relevant_documents(q) if q else []
    ctx = render_docs(docs) or ""

    extracted = extraction.get("extracted", {}) or {}
    text_findings = _scan_text_findings(extracted)
    with metrics.timed("stage_latency", stage="fuse"):
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


async def generate_final_report(case: Dict[str, Any]) -> Dict[str, Any]:
    """Deep advisory report over a full case: recompute the pipeline, then
    Claude (streamed under the hood) with Gemini fallback. Shared by the
    inline finalize route and the queued worker job. Raises RuntimeError
    when no LLM is configured - callers map that to 503 (route) or an
    error status (worker)."""
    import asyncio as _asyncio

    from core.llm_client import (
        anthropic_available, invoke_claude_full, get_llm,
        get_final_model, get_fallback_final_model,
    )

    _, _, details = await _asyncio.to_thread(_recompute_case, case)
    conversation = "\n".join(case.get("utterances", []))
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
            report = await _asyncio.to_thread(_gemini_report)
            model_used = fallback_model
        except Exception as e:
            raise RuntimeError(f"No LLM available for report: {e}")

    return {
        "report": report,
        "model": model_used,
        "fusion": {"top10": details["ranked"], "top_confidence": details["top_conf"],
                   "margin": details["margin"]},
        "disclaimer": "Advisory reference only - not a diagnosis. Correlate clinically.",
    }
