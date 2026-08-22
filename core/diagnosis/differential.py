# -*- coding: utf-8 -*-
"""LLM structured differential diagnosis + validation/cleaning."""

import json
from typing import Any, Dict, List, Optional

from ..config import render_prompt, load_allowed_labels
from ..llm_client import get_llm
from ..utils import parse_llm_json

ALLOWED = set(load_allowed_labels().get("issues_allowed", []))


def generate_structured_differential_diagnosis(
    extraction: Dict[str, Any],
    retrieved_context: str,
    ehr_data: Optional[Dict[str, Any]] = None,
    fusion_results: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generate structured differential diagnosis with enhanced clinical reasoning
    """
    # Prepare context with EHR data if available
    ehr_context = ""
    if ehr_data:
        ehr_context = _format_ehr_for_diagnosis(ehr_data)

    # Prepare fusion context
    fusion_context = ""
    if fusion_results:
        fusion_context = _format_fusion_for_diagnosis(fusion_results)

    prompt = render_prompt(
        "structured_diagnosis",
        allowed_labels=", ".join(sorted(ALLOWED)),
        extraction=json.dumps(extraction.get("extracted", {})),
        context=retrieved_context or "(no context provided)",
        ehr_context=ehr_context,
        fusion_context=fusion_context,
    )

    fallback = {
        "differential_diagnosis": {
            "top_3_diagnoses": [],
            "red_flag_alerts": [],
            "risk_assessment": {
                "overall_risk_level": "unknown",
                "primary_concerns": [],
                "monitoring_required": []
            }
        },
        "clinical_workflow": {
            "ehr_actions": [],
            "order_suggestions": [],
            "follow_up_plan": []
        },
        "citations": []
    }
    try:
        lm = get_llm()
        resp = (lm.invoke_json(prompt) if hasattr(lm, "invoke_json")
                else lm.invoke(prompt)).content
    except Exception as e:
        print(f"⚠️  Structured diagnosis generation error: {e}")
        return fallback

    result = parse_llm_json(resp, fallback)

    # Validate and clean the results
    result = _validate_and_clean_diagnosis(result)

    return result


def _format_ehr_for_diagnosis(ehr_data: Dict[str, Any]) -> str:
    """Format EHR data for diagnosis context"""
    if not ehr_data:
        return ""

    parts = []
    parts.append(f"EHR Patient ID: {ehr_data.get('patient_id', 'Unknown')}")

    # Demographics
    sex = ehr_data.get('sex')
    age = ehr_data.get('age')
    if sex or age:
        parts.append(f"Demographics: {sex or '?'} {age or '?'} years old")

    # Vital signs
    vs = ehr_data.get('vital_signs', {})
    if vs:
        vital_parts = []
        for k, v in vs.items():
            if v is not None:
                vital_parts.append(f"{k}={v}")
        if vital_parts:
            parts.append(f"Vital Signs: {', '.join(vital_parts)}")

    # Past medical history
    pmh = ehr_data.get('pmh', [])
    if pmh:
        parts.append(f"Past Medical History: {', '.join(pmh)}")

    # Medications
    meds = ehr_data.get('meds', [])
    if meds:
        parts.append(f"Current Medications: {', '.join(meds)}")

    # Allergies
    allergies = ehr_data.get('allergies', [])
    if allergies:
        parts.append(f"Allergies: {', '.join(allergies)}")

    # Social history
    social = ehr_data.get('social', {})
    if social:
        social_parts = []
        for k, v in social.items():
            if v:
                social_parts.append(f"{k}={v}")
        if social_parts:
            parts.append(f"Social History: {', '.join(social_parts)}")

    # Clinical notes
    notes = ehr_data.get('ehr_notes')
    if notes:
        parts.append(f"Clinical Notes: {notes}")

    return "\n".join(parts) + "\n\n"


def _format_fusion_for_diagnosis(fusion_results: List[Dict[str, Any]]) -> str:
    """Format fusion results for diagnosis context"""
    if not fusion_results:
        return ""

    parts = ["Fusion Analysis Results:"]
    for i, result in enumerate(fusion_results[:5], 1):
        condition = result.get('condition', 'Unknown')
        score = result.get('score', 0.0)
        why = result.get('why', 'No explanation provided')
        parts.append(f"{i}. {condition} (confidence: {score:.2f}) - {why}")

    return "\n".join(parts) + "\n\n"


def _validate_and_clean_diagnosis(result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean the diagnosis results"""
    # Ensure required structure
    if "differential_diagnosis" not in result:
        result["differential_diagnosis"] = {}

    dd = result["differential_diagnosis"]

    # Clean top 3 diagnoses
    if "top_3_diagnoses" not in dd:
        dd["top_3_diagnoses"] = []

    cleaned_diagnoses = []
    for item in dd["top_3_diagnoses"]:
        if not isinstance(item, dict):
            continue

        condition = item.get("condition", "")
        if condition in ALLOWED:
            cleaned_item = {
                "condition": condition,
                "confidence": max(0.0, min(float(item.get("confidence", 0.0)), 1.0)),
                "likelihood": item.get("likelihood", "unknown"),
                "supporting_evidence": item.get("supporting_evidence", []),
                "risk_factors": item.get("risk_factors", []),
                "ruling_out_evidence": item.get("ruling_out_evidence", []),
                "next_steps": item.get("next_steps", [])
            }
            cleaned_diagnoses.append(cleaned_item)

    dd["top_3_diagnoses"] = cleaned_diagnoses[:3]

    # Clean red flag alerts
    if "red_flag_alerts" not in dd:
        dd["red_flag_alerts"] = []

    cleaned_alerts = []
    for alert in dd["red_flag_alerts"]:
        if isinstance(alert, dict):
            cleaned_alert = {
                "alert_type": alert.get("alert_type", "routine"),
                "condition": alert.get("condition", ""),
                "urgency": alert.get("urgency", "routine"),
                "message": alert.get("message", ""),
                "action_required": alert.get("action_required", ""),
                "time_sensitivity": alert.get("time_sensitivity", "routine")
            }
            cleaned_alerts.append(cleaned_alert)

    dd["red_flag_alerts"] = cleaned_alerts

    # Ensure risk assessment structure
    if "risk_assessment" not in dd:
        dd["risk_assessment"] = {}

    ra = dd["risk_assessment"]
    if "overall_risk_level" not in ra:
        ra["overall_risk_level"] = "unknown"
    if "primary_concerns" not in ra:
        ra["primary_concerns"] = []
    if "monitoring_required" not in ra:
        ra["monitoring_required"] = []

    # Ensure clinical workflow structure
    if "clinical_workflow" not in result:
        result["clinical_workflow"] = {}

    cw = result["clinical_workflow"]
    if "ehr_actions" not in cw:
        cw["ehr_actions"] = []
    if "order_suggestions" not in cw:
        cw["order_suggestions"] = []
    if "follow_up_plan" not in cw:
        cw["follow_up_plan"] = []

    # Ensure citations
    if "citations" not in result:
        result["citations"] = []

    return result
