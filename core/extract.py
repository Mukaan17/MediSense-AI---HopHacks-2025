import os
import re
from typing import Any, Dict, List, Optional, Set

from .config import load_mappings, load_symptom_map
from .llm_client import get_llm
from .utils import parse_llm_json


NEGATION_RE = re.compile(r"\b(no|not|denies|denied|without|never)\b", re.IGNORECASE)

_DEFAULT_TRAUMA = [
    "fall",
    "fell",
    "injury",
    "impact",
    "hit",
    "trauma",
    "accident",
    "fracture",
    "broken",
    "bruise",
    "contusion",
]

_DEFAULT_INFECTIOUS = [
    "fever",
    "cough",
    "chills",
    "sputum",
    "phlegm",
    "productive cough",
    "congestion",
    "infection",
    "sore throat",
]


def _dedupe_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        v = str(item).strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[\n\r]+|(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _is_negated(sentence: str, phrase: str) -> bool:
    s = sentence.lower()
    p = phrase.lower()
    if p not in s:
        return False
    i = s.find(p)
    window = s[max(0, i - 24) : i]
    return bool(NEGATION_RE.search(window))


def _find_duration(text: str) -> Optional[str]:
    patterns = [
        r"\bfor\s+(\d+\s*(?:minutes?|hours?|days?|weeks?|months?|years?))\b",
        r"\b(\d+\s*(?:minutes?|hours?|days?|weeks?|months?|years?))\s+ago\b",
        r"\bsince\s+([a-zA-Z0-9\-\s]+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_blood_pressure(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{2,3}/\d{2,3})\b", text)
    return m.group(1) if m else None


def _extract_temperature(text: str) -> Optional[str]:
    m = re.search(r"\b(temp(?:erature)?\s*(?:is|of)?\s*\d{2,3}(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _extract_pmh(text: str) -> List[str]:
    out: List[str] = []
    patterns = [
        r"\b(?:history of|hx of|known)\s+([a-zA-Z0-9,\-\s/]+)",
        r"\b(?:past medical history|pmh)\s*[:\-]?\s*([a-zA-Z0-9,\-\s/]+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            raw = m.group(1).strip(" .")
            for token in re.split(r",|/| and ", raw):
                t = token.strip(" .")
                if t:
                    out.append(t)
    return _dedupe_keep_order(out)


def _extract_meds(text: str) -> List[str]:
    out: List[str] = []
    patterns = [
        r"\b(?:taking|takes|on|medication|medications|meds)\s+([a-zA-Z0-9,\-\s/]+)",
        r"\b([A-Za-z][A-Za-z0-9\-]{2,}\s+\d+(?:\.\d+)?\s*mg)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            raw = m.group(1).strip(" .")
            for token in re.split(r",|/| and ", raw):
                t = token.strip(" .")
                if not t:
                    continue
                if len(t.split()) <= 5:
                    out.append(t)
    return _dedupe_keep_order(out)


def _collect_symptom_phrases() -> Set[str]:
    phrases: Set[str] = set()
    symptom_map = load_symptom_map() or {}
    mappings = load_mappings() or {}
    synonyms = mappings.get("synonyms_to_issue") or {}

    for _, kws in symptom_map.items():
        for kw in (kws or []):
            s = str(kw).strip().lower()
            if len(s) >= 3:
                phrases.add(s)

    for syn in synonyms.keys():
        s = str(syn).strip().lower()
        if len(s) >= 3:
            phrases.add(s)

    # Safety baseline for common clinical dialogue.
    phrases.update(
        {
            "chest pain",
            "chest discomfort",
            "shortness of breath",
            "difficulty breathing",
            "dyspnea",
            "cough",
            "fever",
            "fatigue",
            "dizziness",
            "lightheaded",
            "headache",
            "nausea",
            "vomiting",
            "palpitations",
        }
    )
    return phrases


def _load_signal_groups() -> Dict[str, List[str]]:
    mappings = load_mappings() or {}
    trauma = [str(x).strip().lower() for x in (mappings.get("trauma_cues") or _DEFAULT_TRAUMA)]
    infectious = [str(x).strip().lower() for x in (mappings.get("infectious_cues") or _DEFAULT_INFECTIOUS)]
    return {
        "symptoms": sorted(_collect_symptom_phrases(), key=len, reverse=True),
        "trauma": _dedupe_keep_order(trauma),
        "infectious": _dedupe_keep_order(infectious),
    }


def _extract_symptoms(sentences: List[str], signals: Dict[str, List[str]]) -> Dict[str, List[str]]:
    symptoms: List[str] = []
    trauma: List[str] = []
    infectious: List[str] = []
    negated: List[str] = []

    symptom_phrases = signals.get("symptoms") or []
    trauma_cues = signals.get("trauma") or []
    infectious_cues = signals.get("infectious") or []

    for sent in sentences:
        lower = sent.lower()
        for phrase in symptom_phrases:
            if phrase in lower:
                if _is_negated(lower, phrase):
                    negated.append(phrase)
                else:
                    symptoms.append(phrase)

        for cue in trauma_cues:
            if re.search(r"\b" + re.escape(cue) + r"\b", lower):
                if _is_negated(lower, cue):
                    negated.append(cue)
                else:
                    trauma.append(cue)

        for cue in infectious_cues:
            if re.search(r"\b" + re.escape(cue) + r"\b", lower):
                if _is_negated(lower, cue):
                    negated.append(cue)
                else:
                    infectious.append(cue)

    return {
        "symptoms": _dedupe_keep_order(symptoms),
        "trauma_cues": _dedupe_keep_order(trauma),
        "infectious_cues": _dedupe_keep_order(infectious),
        "negated_findings": _dedupe_keep_order(negated),
    }


def _synthesize_query(extracted: Dict[str, Any], fallback_text: str) -> str:
    pieces: List[str] = []
    for k in ("chief_complaint", "duration"):
        v = extracted.get(k)
        if v:
            pieces.append(str(v))
    for k in ("symptoms", "trauma_cues", "infectious_cues", "possible_pmh", "possible_meds"):
        vals = extracted.get(k) or []
        for v in vals:
            pieces.append(str(v))

    query = "; ".join(_dedupe_keep_order(pieces))
    query = query.strip()
    if not query:
        return fallback_text[:500]
    return query[:500]


def _extract_llm_optional(text: str) -> Dict[str, Any]:
    if os.getenv("EXTRACTOR_USE_LLM", "false").strip().lower() not in {"1", "true", "yes"}:
        return {}
    try:
        prompt = (
            "Extract structured clinical fields from this dialogue and return STRICT JSON only.\n"
            "Schema: {"
            "\"chief_complaint\": string,"
            "\"symptoms\": string[],"
            "\"duration\": string|null,"
            "\"possible_pmh\": string[],"
            "\"possible_meds\": string[],"
            "\"trauma_cues\": string[],"
            "\"infectious_cues\": string[],"
            "\"negated_findings\": string[]"
            "}.\n"
            f"Dialogue:\n{text}"
        )
        resp = get_llm().invoke(prompt).content.strip()
        if not resp:
            return {}
        return parse_llm_json(resp, {})
    except Exception:
        return {}


def _merge_llm_extraction(base: Dict[str, Any], llm_out: Dict[str, Any]) -> Dict[str, Any]:
    if not llm_out:
        return base

    merged = dict(base)
    for k in ("chief_complaint", "duration"):
        if not merged.get(k) and llm_out.get(k):
            merged[k] = llm_out.get(k)
    for k in ("symptoms", "possible_pmh", "possible_meds", "trauma_cues", "infectious_cues", "negated_findings"):
        vals = list(merged.get(k) or [])
        vals.extend([str(x) for x in (llm_out.get(k) or []) if str(x).strip()])
        merged[k] = _dedupe_keep_order(vals)
    return merged


def extractor_generate(conversation: str) -> Dict[str, Any]:
    """Deterministic extraction with optional LLM assist (`EXTRACTOR_USE_LLM=true`)."""
    try:
        text = (conversation or "").strip()
        if not text:
            return {"extracted": {}, "retrieval_query": ""}

        sentences = _split_sentences(text)
        signals = _load_signal_groups()
        cue_block = _extract_symptoms(sentences, signals)

        symptoms = list(cue_block["symptoms"])
        bp = _extract_blood_pressure(text)
        if bp:
            symptoms.append(f"bp {bp}")
        temp = _extract_temperature(text)
        if temp:
            symptoms.append(temp.lower())
        symptoms = _dedupe_keep_order(symptoms)

        chief_complaint = symptoms[0] if symptoms else (sentences[0][:140] if sentences else "")
        duration = _find_duration(text)
        pmh = _extract_pmh(text)
        meds = _extract_meds(text)

        extracted = {
            "chief_complaint": chief_complaint,
            "symptoms": symptoms,
            "duration": duration,
            "possible_pmh": pmh,
            "possible_meds": meds,
            "trauma_cues": cue_block["trauma_cues"],
            "infectious_cues": cue_block["infectious_cues"],
            "negated_findings": cue_block["negated_findings"],
        }

        extracted = _merge_llm_extraction(extracted, _extract_llm_optional(text))
        query = _synthesize_query(extracted, text)
        return {"extracted": extracted, "retrieval_query": query}
    except Exception:
        return {"extracted": {}, "retrieval_query": (conversation or "")}
