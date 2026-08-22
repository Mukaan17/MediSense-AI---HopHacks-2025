import json
import os
from typing import Any, AsyncIterator, Dict, List

from .llm_client import get_llm

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# Clinical guardrail: questions containing prescriptive language never reach
# the clinician UI, whichever model generated them. Patterns target actual
# prescriptive instructions (dosing, prescribing, telling the patient to
# take/start medication) - bare substrings like 'take'/'start' would filter
# legitimate questions such as "When did the symptoms start?".
import re as _re

PRESCRIPTIVE_PATTERNS = tuple(_re.compile(p) for p in (
    r"\b\d+\s?(mg|mcg|ml|milligrams?|micrograms?|units?)\b",
    r"\bprescri(be|bed|bing|ption)\b",
    r"\bdos(e|es|ing|age)\b",
    r"\b(take|start|begin)\b[^.?!]*\b(medication|medicine|pill|tablet|antibiotic|aspirin|drug)s?\b",
    r"\bdiagnos(e|ed|ing)\s+you\b",
))


def is_prescriptive(text: str) -> bool:
    lowered = (text or "").lower()
    return any(p.search(lowered) for p in PRESCRIPTIVE_PATTERNS)

SYSTEM = (
    "You are a clinical question generator for a chest-focused advisory system. "
    "You DO NOT diagnose or prescribe. You generate brief, high-yield clarifying "
    "questions that increase information for the current leading differential, "
    "prioritizing red flags first. You must return STRICT JSON only."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "priority": {"type": "string", "enum": ["red-flag", "triage", "disposition", "detail"]},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "info_gain": {"type": "number", "minimum": 0, "maximum": 1},
                    "why": {"type": "string"},
                },
                "required": ["q", "priority", "targets", "info_gain", "why"],
            },
        }
    },
    "required": ["questions"],
}

PROMPT = """You will be given the current case STATE as JSON.

GOAL
- Propose 1–4 clarifying questions that most increase information for the current leading conditions.
- Prioritize red flags and safety first.
- Keep questions concise (<= 18 words), patient-friendly, and single-intent.

CONSTRAINTS
- Advisory-only. No diagnoses, no medication or dosing advice.
- Chest is the end scope, but you may ask broad triage questions ONLY if confidence in chest is low.
- Use retrieved_context to tailor questions; do not copy long text.

RETURN
- STRICT JSON matching this schema:
{schema}

STATE
{state}
"""


def propose_questions_llm(state: Dict[str, Any], max_questions: int = 4) -> List[Dict[str, Any]]:
    state = dict(state or {})
    state["max_questions"] = max_questions
    lm = get_llm(model=GEMINI_MODEL, temperature=TEMPERATURE)
    msg = PROMPT.format(schema=json.dumps(SCHEMA, indent=2), state=json.dumps(state, ensure_ascii=False))
    out = lm.invoke(f"{SYSTEM}\n\n{msg}").content.strip()

    try:
        data = json.loads(out)
    except Exception:
        try:
            cleaned_resp = out.strip()
            if cleaned_resp.startswith("```json"):
                cleaned_resp = cleaned_resp[7:]
            if cleaned_resp.startswith("```"):
                cleaned_resp = cleaned_resp[3:]
            if cleaned_resp.endswith("```"):
                cleaned_resp = cleaned_resp[:-3]

            start_idx = cleaned_resp.find("{")
            end_idx = cleaned_resp.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = cleaned_resp[start_idx : end_idx + 1]
                data = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No JSON found in cleaned response", cleaned_resp, 0)
        except Exception:
            start, end = out.find("{"), out.rfind("}")
            data = json.loads(out[start : end + 1]) if start >= 0 and end > start else {"questions": []}

    qs = data.get("questions", [])[:max_questions]
    clean = []
    for q in qs:
        txt = (q.get("q", "") or "").strip()
        if not txt:
            continue
        if is_prescriptive(txt):
            continue
        pr = q.get("priority", "detail")
        if pr not in {"red-flag", "triage", "disposition", "detail"}:
            pr = "detail"
        tg = q.get("targets", []) or []
        ig = float(q.get("info_gain", 0.5))
        why = (q.get("why", "") or "")[:140]
        clean.append({"q": txt, "priority": pr, "targets": tg[:3], "info_gain": max(0, min(1, ig)), "why": why})
    return clean[:max_questions]


STREAM_SYSTEM = (
    "You are a concise clinical question generator for an advisory system. "
    "You DO NOT diagnose or prescribe. Output only short bullet-point "
    "clarifying questions a clinician should ask next, red flags first."
)


async def stream_live_suggestions(state: Dict[str, Any], model: str = None) -> AsyncIterator[str]:
    """Yield text tokens of 1-3 bullet-point clarifying questions via Claude.

    Callers must run the final text through parse_bullet_questions(), which
    applies the prescriptive-language guardrail."""
    from .llm_client import stream_claude_tokens

    prompt = (
        "Given this partial clinical state, generate 1-3 short follow-up "
        "questions a clinician should ask, each on its own line as a bullet "
        "point. Prefix any urgent safety-screening question with the tag "
        "[red-flag]. Questions only - no headers, no JSON, no advice.\n\n"
        f"STATE: {json.dumps(state, ensure_ascii=False, default=str)[:1500]}"
    )
    async for token in stream_claude_tokens(prompt, model=model, system=STREAM_SYSTEM):
        yield token


def parse_bullet_questions(text: str, max_questions: int = 3) -> List[Dict[str, Any]]:
    """Parse streamed bullet lines into the question dict shape used by the
    HUD, applying the same prescriptive-language filter as the JSON path."""
    questions: List[Dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("•-*").strip()
        if not line or len(line) < 4:
            continue
        priority = "detail"
        if line.lower().startswith("[red-flag]"):
            priority = "red-flag"
            line = line[len("[red-flag]"):].strip()
        if not line or is_prescriptive(line):
            continue
        questions.append({
            "q": line,
            "priority": priority,
            "targets": [],
            "info_gain": 0.5,
            "why": "",
        })
        if len(questions) >= max_questions:
            break
    # Red flags first, mirroring the JSON path's ordering contract.
    questions.sort(key=lambda q: 0 if q["priority"] == "red-flag" else 1)
    return questions
