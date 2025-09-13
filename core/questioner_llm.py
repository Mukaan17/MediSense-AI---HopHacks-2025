# core/questioner_llm.py
import json, os
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage

# Reuse your env: GROQ_API_KEY, default model
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

def _llm():
    return ChatGroq(model=GROQ_MODEL, temperature=TEMPERATURE)

SYSTEM = (
  "You are a clinical question generator for a chest-focused advisory system. "
  "You DO NOT diagnose or prescribe. You generate brief, high-yield clarifying "
  "questions that increase information for the current leading differential, "
  "prioritizing red flags first. You must return STRICT JSON only."
)

# Strict JSON schema the UI/server expects
SCHEMA = {
  "type": "object",
  "properties": {
    "questions": {
      "type":"array",
      "items":{
        "type":"object",
        "properties":{
          "q":{"type":"string"},
          "priority":{"type":"string","enum":["red-flag","triage","disposition","detail"]},
          "targets":{"type":"array","items":{"type":"string"}},
          "info_gain":{"type":"number","minimum":0,"maximum":1},
          "why":{"type":"string"}
        },
        "required":["q","priority","targets","info_gain","why"]
      }
    }
  },
  "required":["questions"]
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
    lm = _llm()
    msg = PROMPT.format(schema=json.dumps(SCHEMA, indent=2), state=json.dumps(state, ensure_ascii=False))
    out = lm([SystemMessage(content=SYSTEM), HumanMessage(content=msg)]).content.strip()

    # robust JSON recovery
    try:
        data = json.loads(out)
    except Exception:
        # brace-recovery fallback
        start, end = out.find("{"), out.rfind("}")
        data = json.loads(out[start:end+1]) if start >= 0 and end > start else {"questions":[]}

    qs = data.get("questions", [])[:max_questions]
    # light guardrails
    clean = []
    for q in qs:
        txt = (q.get("q","") or "").strip()
        if not txt: continue
        if any(w in txt.lower() for w in ["take", "start", "mg", "dose", "prescribe", "diagnose"]):  # safety
            continue
        pr = q.get("priority","detail")
        if pr not in {"red-flag","triage","disposition","detail"}: pr = "detail"
        tg = q.get("targets",[]) or []
        ig = float(q.get("info_gain", 0.5))
        why = (q.get("why","") or "")[:140]
        clean.append({"q": txt, "priority": pr, "targets": tg[:3], "info_gain": max(0,min(1,ig)), "why": why})
    return clean[:max_questions]
