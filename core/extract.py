# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 12:41:23
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:32
import json
import re
from typing import Dict, Any
from .config import load_prompt
from .llm_client import get_llm

BP_PATTERN = re.compile(r"\b(?:bp\s*)?(\d{2,3}/\d{2,3})\b", re.IGNORECASE)

def extractor_generate(dialogue_text: str) -> Dict[str, Any]:
    prompt_tmpl = load_prompt("extract")
    prompt = prompt_tmpl.replace("{{ dialogue }}", dialogue_text)
    
    try:
        resp = get_llm().invoke(prompt).content
    except Exception as e:
        print(f"LLM extraction error: {e}")
        return {
            "extracted": {"chief_complaint": "", "symptoms": [], "duration": None, "possible_pmh": [], "possible_meds": []},
            "retrieval_query": dialogue_text[:200]
        }
    
    try:
        data = json.loads(resp)
    except Exception as e:
        print(f"JSON parsing error in extraction: {e}")
        print(f"Response: {resp[:200]}...")
        i, j = resp.find("{"), resp.rfind("}")
        try:
            data = json.loads(resp[i:j+1]) if i != -1 and j != -1 and j > i else {
                "extracted": {"chief_complaint": "", "symptoms": [], "duration": None, "possible_pmh": [], "possible_meds": []},
                "retrieval_query": dialogue_text[:200]
            }
        except Exception:
            data = {
                "extracted": {"chief_complaint": "", "symptoms": [], "duration": None, "possible_pmh": [], "possible_meds": []},
                "retrieval_query": dialogue_text[:200]
            }

    # Ensure numeric vitals appear verbatim in symptoms
    symptoms = data.get("extracted", {}).get("symptoms", []) or []
    for m in BP_PATTERN.findall(dialogue_text):
        token = f"bp {m.lower()}"
        if token not in [s.lower() for s in symptoms]:
            symptoms.append(token)
    data.setdefault("extracted", {})
    data["extracted"]["symptoms"] = symptoms
    data.setdefault("retrieval_query", dialogue_text[:200])
    return data


