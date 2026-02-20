import math
import re
from typing import Any, Dict, List, Optional

from .config import load_allowed_labels, load_mappings

_map = load_mappings() or {}
_img_map_raw = _map.get("imaging_to_issue", {}) or {}
_allowed = set((load_allowed_labels() or {}).get("issues_allowed", []) or [])

INFECTION_ISSUES = {
    "pneumonia_unspecified",
    "upper_respiratory_infection",
    "influenza_like_illness",
    "covid19_suspected",
}

TRAUMA_ISSUES = {
    "musculoskeletal_chest_pain",
    "pneumothorax_red_flags",
}


def _canon(v: Any) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


IMG2ISSUE = {
    _canon(k): _canon(v)
    for k, v in _img_map_raw.items()
    if _canon(k) and _canon(v)
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(float(p), eps), 1.0 - eps)
    return math.log(p / (1.0 - p))


def _coerce_score(v: Any, default: float = 0.5) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    return min(max(x, 0.0), 1.0)


def _can_add_issue(issue: str, existing: Dict[str, float]) -> bool:
    if issue in existing:
        return True
    if not _allowed:
        return True
    return issue in _allowed


def _map_img_label(label: Any) -> str:
    c = _canon(label)
    return IMG2ISSUE.get(c) or c


def _ehr_signals(ehr: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not ehr:
        return out

    vs = ehr.get("vital_signs") or {}
    temp = vs.get("temp_f")
    spo2 = vs.get("spo2_pct")
    hr = vs.get("hr")
    bp = str(vs.get("bp") or "")

    if temp is not None:
        try:
            if float(temp) >= 100.4:
                out.append({"issue": "pneumonia_unspecified", "contribution": 0.22, "reason": f"fever {temp}F"})
        except Exception:
            pass
    if spo2 is not None:
        try:
            if float(spo2) < 94:
                out.append({"issue": "pneumonia_unspecified", "contribution": 0.18, "reason": f"low spo2 {spo2}%"})
        except Exception:
            pass
    if hr is not None:
        try:
            if float(hr) > 110:
                out.append({"issue": "acute_coronary_syndrome_suspected", "contribution": 0.10, "reason": f"tachycardia {hr}"})
        except Exception:
            pass
    if bp and re.search(r"\b(1[89]\d|2\d\d)/(\d{2,3})\b", bp):
        out.append({"issue": "hypertension_uncontrolled", "contribution": 0.20, "reason": f"elevated bp {bp}"})

    pmh = [str(x).lower() for x in (ehr.get("pmh") or [])]
    if any(t in " ".join(pmh) for t in ["copd", "asthma"]):
        out.append({"issue": "copd_exacerbation", "contribution": 0.08, "reason": "pmh includes obstructive lung disease"})
    if any(t in " ".join(pmh) for t in ["fracture", "fall", "trauma"]):
        out.append({"issue": "musculoskeletal_chest_pain", "contribution": 0.10, "reason": "pmh includes trauma/fracture"})

    return out


def build_evidence(
    image_findings: List[Dict[str, Any]],
    text_findings: List[Dict[str, Any]],
    ehr: Optional[Dict[str, Any]],
    extracted: Optional[Dict[str, Any]],
    fused_ranked: Optional[List[Dict[str, Any]]] = None,
    topk: int = 10,
) -> Dict[str, Any]:
    """Build explainable posterior shift over fused outputs.

    This intentionally stays deterministic and low-latency for live endpoints.
    """
    base_probs: Dict[str, float] = {}
    for r in (fused_ranked or []):
        issue = _canon(r.get("condition"))
        if not issue:
            continue
        base_probs[issue] = _coerce_score(r.get("score"), 0.5)

    logits: Dict[str, float] = {k: _logit(v) for k, v in base_probs.items()}
    image_evidence: List[Dict[str, Any]] = []
    text_evidence: List[Dict[str, Any]] = []
    ehr_evidence: List[Dict[str, Any]] = []
    shift_reasons: List[str] = []

    # Image evidence contribution (small, because fused score already includes image signal).
    for f in (image_findings or []):
        issue = _map_img_label(f.get("label"))
        score = _coerce_score(f.get("score", f.get("prob", 0.5)))
        if not issue or not _can_add_issue(issue, logits):
            continue
        contrib = round((score - 0.5) * 0.24, 4)
        logits[issue] = logits.get(issue, 0.0) + contrib
        image_evidence.append(
            {
                "label": f.get("label"),
                "issue": issue,
                "score": score,
                "contribution": contrib,
            }
        )

    # Text findings contribution.
    for tf in (text_findings or []):
        issue = _canon(tf.get("label"))
        if not issue or not _can_add_issue(issue, logits):
            continue
        evid = [str(x) for x in (tf.get("evidence") or [])]
        strength = min(0.42, 0.14 + 0.06 * len(evid))
        logits[issue] = logits.get(issue, 0.0) + strength
        text_evidence.append(
            {
                "issue": issue,
                "evidence": evid,
                "contribution": round(strength, 4),
            }
        )

    extracted = extracted or {}
    trauma_cues = [str(x) for x in (extracted.get("trauma_cues") or [])]
    infectious_cues = [str(x) for x in (extracted.get("infectious_cues") or [])]

    # Contradiction-aware shift: trauma cues reduce infection-heavy hypotheses.
    if trauma_cues:
        trauma_strength = min(0.9, 0.24 * len(trauma_cues))
        for issue in TRAUMA_ISSUES:
            if _can_add_issue(issue, logits):
                logits[issue] = logits.get(issue, 0.0) + trauma_strength
                text_evidence.append(
                    {
                        "issue": issue,
                        "evidence": trauma_cues,
                        "contribution": round(trauma_strength, 4),
                    }
                )
        for issue in INFECTION_ISSUES:
            if issue in logits:
                penalty = 0.34 * trauma_strength
                logits[issue] = logits.get(issue, 0.0) - penalty
        shift_reasons.append("Trauma cues present; down-weighted infection-centric hypotheses.")

    if infectious_cues:
        inf_strength = min(0.9, 0.22 * len(infectious_cues))
        for issue in INFECTION_ISSUES:
            if _can_add_issue(issue, logits):
                logits[issue] = logits.get(issue, 0.0) + inf_strength
                text_evidence.append(
                    {
                        "issue": issue,
                        "evidence": infectious_cues,
                        "contribution": round(inf_strength, 4),
                    }
                )
        for issue in TRAUMA_ISSUES:
            if issue in logits:
                logits[issue] = logits.get(issue, 0.0) - (0.25 * inf_strength)
        shift_reasons.append("Infectious cues present; reinforced infection-centric hypotheses.")

    for s in _ehr_signals(ehr):
        issue = _canon(s.get("issue"))
        contrib = float(s.get("contribution", 0.0))
        if not issue or not _can_add_issue(issue, logits):
            continue
        logits[issue] = logits.get(issue, 0.0) + contrib
        ehr_evidence.append(
            {
                "issue": issue,
                "reason": s.get("reason"),
                "contribution": round(contrib, 4),
            }
        )

    adjusted_probs = {k: _sigmoid(v) for k, v in logits.items()}
    adjusted_top10 = sorted(
        [{"condition": k, "score": round(float(v), 4), "why": "evidence-adjusted multimodal posterior"} for k, v in adjusted_probs.items()],
        key=lambda x: x["score"],
        reverse=True,
    )[:topk]

    all_issues = set(base_probs) | set(adjusted_probs)
    deltas = []
    for issue in all_issues:
        before = base_probs.get(issue, 0.5)
        after = adjusted_probs.get(issue, before)
        deltas.append(
            {
                "condition": issue,
                "before": round(float(before), 4),
                "after": round(float(after), 4),
                "shift": round(float(after - before), 4),
            }
        )
    deltas.sort(key=lambda x: abs(x["shift"]), reverse=True)

    base_top = sorted(base_probs.items(), key=lambda kv: kv[1], reverse=True)
    base_top_obj = {"condition": base_top[0][0], "score": round(float(base_top[0][1]), 4)} if base_top else None
    adj_top_obj = adjusted_top10[0] if adjusted_top10 else None

    return {
        "image_evidence": image_evidence,
        "text_evidence": text_evidence,
        "ehr_evidence": ehr_evidence,
        "posterior_shift": {
            "base_top": base_top_obj,
            "adjusted_top": adj_top_obj,
            "delta": deltas[:10],
            "shift_reasons": shift_reasons,
            "adjusted_top10": adjusted_top10,
        },
    }
