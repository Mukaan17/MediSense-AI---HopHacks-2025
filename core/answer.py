import json
from typing import Dict, Any
from .config import load_prompt, load_allowed_labels
from .llm_client import get_llm

ALLOWED = set(load_allowed_labels().get("issues_allowed", []))

def answerer_generate(extraction: Dict[str, Any], retrieved_context: str) -> Dict[str, Any]:
    prompt_tmpl = load_prompt("answer")
    prompt = (
        prompt_tmpl
        .replace("{{ allowed_labels }}", ", ".join(sorted(ALLOWED)))
        .replace("{{ extraction }}", json.dumps(extraction.get("extracted", {})))
        .replace("{{ context }}", retrieved_context or "(no context provided)")
    )

    resp = get_llm().invoke(prompt).content
    fallback = {
        "potential_issues_ranked": [],
        "red_flags_to_screen": [],
        "follow_up": "",
        "citations": []
    }
    try:
        answer = json.loads(resp)
    except Exception:
        i, j = resp.find("{"), resp.rfind("}")
        answer = json.loads(resp[i:j+1]) if i != -1 and j != -1 and j > i else fallback

    # Closed-set + clamp + top-3
    cleaned = []
    for item in answer.get("potential_issues_ranked", []):
        cond = (item or {}).get("condition", "")
        if cond in ALLOWED:
            why = (item or {}).get("why", "")
            try:
                conf = float((item or {}).get("confidence", 0.0))
            except Exception:
                conf = 0.0
            cleaned.append({"condition": cond, "why": why, "confidence": max(0.0, min(conf, 1.0))})
    answer["potential_issues_ranked"] = cleaned[:3]

    # Strip non-prescriptive steps from output entirely per product requirement
    answer.pop("first_steps_non_prescriptive", None)

    if not answer.get("citations"):
        answer["citations"] = []
    return answer


