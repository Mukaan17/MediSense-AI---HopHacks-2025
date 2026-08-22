# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 12:41:23
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:34
import json
from typing import Dict, Any
from .config import render_prompt, load_allowed_labels
from .llm_client import get_llm
from .utils import parse_llm_json

ALLOWED = set(load_allowed_labels().get("issues_allowed", []))

def answerer_generate(extraction: Dict[str, Any], retrieved_context: str) -> Dict[str, Any]:
    prompt = render_prompt(
        "answer",
        allowed_labels=", ".join(sorted(ALLOWED)),
        extraction=json.dumps(extraction.get("extracted", {})),
        context=retrieved_context or "(no context provided)",
    )

    fallback = {
        "potential_issues_ranked": [],
        "red_flags_to_screen": [],
        "follow_up": "",
        "citations": []
    }
    
    try:
        resp = get_llm().invoke(prompt).content
    except Exception as e:
        print(f"LLM answer generation error: {e}")
        return fallback
    
    answer = parse_llm_json(resp, fallback)

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


