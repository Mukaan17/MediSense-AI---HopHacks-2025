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
        print(f"Response (first 200 chars): {resp[:200]}...")
        print(f"Response length: {len(resp)} chars")
        
        # Try to extract JSON from markdown code blocks first
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
                data = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No JSON found in cleaned response", cleaned_resp, 0)
        except Exception:
            # Fallback to original method
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


