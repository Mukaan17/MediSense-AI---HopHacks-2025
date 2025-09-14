# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 12:41:23
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:34
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
    
    try:
        # Try to parse the response directly
        answer = json.loads(resp)
    except Exception as e:
        print(f"JSON parsing error in answer generation: {e}")
        print(f"Raw response (first 200 chars): {resp[:200]}...")
        print(f"Response length: {len(resp)} chars")
        
        # Try to extract JSON from markdown code blocks
        try:
            # Remove markdown code block markers
            cleaned_resp = resp.strip()
            if cleaned_resp.startswith("```json"):
                cleaned_resp = cleaned_resp[7:]  # Remove ```json
            if cleaned_resp.startswith("```"):
                cleaned_resp = cleaned_resp[3:]   # Remove ```
            if cleaned_resp.endswith("```"):
                cleaned_resp = cleaned_resp[:-3]  # Remove trailing ```
            
            # Try to find JSON object boundaries
            start_idx = cleaned_resp.find("{")
            end_idx = cleaned_resp.rfind("}")
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = cleaned_resp[start_idx:end_idx+1]
                answer = json.loads(json_str)
            else:
                answer = fallback
        except Exception as e2:
            print(f"Failed to extract JSON from markdown: {e2}")
            answer = fallback

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


