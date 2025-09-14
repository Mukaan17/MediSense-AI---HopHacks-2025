# -*- coding: utf-8 -*-
# @Author: Mukhil Sundararaj
# @Date:   2025-09-13 16:17:31
# @Last Modified by:   Mukhil Sundararaj
# @Last Modified time: 2025-09-13 17:10:29
"""
Enhanced Clinical Diagnosis Module
Provides structured differential diagnosis with risk factors, red flags, and clinical workflow integration
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple
from .config import load_prompt, load_allowed_labels
from .llm_client import get_llm

ALLOWED = set(load_allowed_labels().get("issues_allowed", []))

def generate_brief_diagnosis_summary(
    extraction: Dict[str, Any],
    fusion_results: Optional[List[Dict[str, Any]]] = None,
    max_sentences: int = 2
) -> str:
    """
    Produce a concise 1–2 line diagnostic summary using LLM knowledge, grounded in
    extracted findings and (optionally) fused image/text candidates.
    """
    llm = get_llm()
    extracted_json = json.dumps(extraction.get("extracted", {}))
    top_lines = []
    for i, r in enumerate((fusion_results or [])[:3], 1):
        cond = r.get("condition", "")
        sc = r.get("score", 0.0)
        if cond:
            top_lines.append(f"{i}. {cond} ({sc:.2f})")
    top_text = "\n".join(top_lines)

    prompt = (
        "You are a careful clinical summarizer. Given structured extraction and top candidates, "
        f"write <= {max_sentences} sentences that neutrally summarize the likely working diagnosis. "
        "Do NOT prescribe. Be concise and advisory.\n\n"
        f"Extracted: {extracted_json}\n"
        f"Top candidates:\n{top_text}\n\n"
        "Summary:"
    )
    try:
        out = llm.invoke(prompt)
        text = (getattr(out, "content", None) or str(out)).strip()
        # Hard truncate to ~300 chars for safety
        return text[:300]
    except Exception:
        return "Concise diagnostic summary is unavailable right now."

def generate_structured_differential_diagnosis(
    extraction: Dict[str, Any], 
    retrieved_context: str,
    ehr_data: Optional[Dict[str, Any]] = None,
    fusion_results: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generate structured differential diagnosis with enhanced clinical reasoning
    """
    # Load enhanced prompt for structured diagnosis
    prompt_tmpl = load_prompt("structured_diagnosis")
    
    # Prepare context with EHR data if available
    ehr_context = ""
    if ehr_data:
        ehr_context = _format_ehr_for_diagnosis(ehr_data)
    
    # Prepare fusion context
    fusion_context = ""
    if fusion_results:
        fusion_context = _format_fusion_for_diagnosis(fusion_results)
    
    prompt = (
        prompt_tmpl
        .replace("{{ allowed_labels }}", ", ".join(sorted(ALLOWED)))
        .replace("{{ extraction }}", json.dumps(extraction.get("extracted", {})))
        .replace("{{ context }}", retrieved_context or "(no context provided)")
        .replace("{{ ehr_context }}", ehr_context)
        .replace("{{ fusion_context }}", fusion_context)
    )

    resp = get_llm().invoke(prompt).content
    
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
        result = json.loads(resp)
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parsing error: {e}")
        print(f"⚠️  Raw response (first 200 chars): {resp[:200]}...")
        print(f"⚠️  Response length: {len(resp)} chars")
        
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
                result = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No JSON found in cleaned response", cleaned_resp, 0)
        except json.JSONDecodeError:
            # Fallback to original method
            i, j = resp.find("{"), resp.rfind("}")
            if i != -1 and j != -1 and j > i:
                try:
                    result = json.loads(resp[i:j+1])
                except json.JSONDecodeError:
                    print("⚠️  Failed to extract valid JSON, using fallback")
                    result = fallback
            else:
                print("⚠️  No JSON found in response, using fallback")
                result = fallback
    
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

def analyze_risk_factors(
    extraction: Dict[str, Any], 
    ehr_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Analyze risk factors from patient data
    """
    risk_factors = []
    
    # Age-based risks
    if ehr_data and ehr_data.get('age'):
        age = ehr_data['age']
        if age >= 65:
            risk_factors.append({
                "factor": "age",
                "value": str(age),
                "risk_level": "moderate",
                "description": "Advanced age increases risk for multiple conditions"
            })
        elif age >= 50:
            risk_factors.append({
                "factor": "age", 
                "value": str(age),
                "risk_level": "low",
                "description": "Middle age with moderate risk increase"
            })
    
    # Gender-based risks
    if ehr_data and ehr_data.get('sex'):
        sex = ehr_data['sex']
        if sex == 'M':
            risk_factors.append({
                "factor": "gender",
                "value": "male",
                "risk_level": "low",
                "description": "Male gender increases risk for cardiovascular conditions"
            })
    
    # Vital signs risks
    if ehr_data and ehr_data.get('vital_signs'):
        vs = ehr_data['vital_signs']
        
        # Blood pressure
        bp = vs.get('bp')
        if bp:
            bp_match = re.search(r'(\d+)/(\d+)', str(bp))
            if bp_match:
                systolic = int(bp_match.group(1))
                diastolic = int(bp_match.group(2))
                
                if systolic >= 180 or diastolic >= 110:
                    risk_factors.append({
                        "factor": "blood_pressure",
                        "value": bp,
                        "risk_level": "critical",
                        "description": "Hypertensive crisis - immediate attention required"
                    })
                elif systolic >= 140 or diastolic >= 90:
                    risk_factors.append({
                        "factor": "blood_pressure",
                        "value": bp,
                        "risk_level": "high",
                        "description": "Elevated blood pressure"
                    })
        
        # Heart rate
        hr = vs.get('hr')
        if hr:
            if hr > 100:
                risk_factors.append({
                    "factor": "heart_rate",
                    "value": str(hr),
                    "risk_level": "moderate",
                    "description": "Tachycardia"
                })
            elif hr < 60:
                risk_factors.append({
                    "factor": "heart_rate",
                    "value": str(hr),
                    "risk_level": "low",
                    "description": "Bradycardia"
                })
        
        # Temperature
        temp = vs.get('temp_f')
        if temp:
            if temp > 100.4:
                risk_factors.append({
                    "factor": "temperature",
                    "value": f"{temp}°F",
                    "risk_level": "moderate",
                    "description": "Fever - possible infection"
                })
        
        # Oxygen saturation
        spo2 = vs.get('spo2_pct')
        if spo2:
            if spo2 < 95:
                risk_factors.append({
                    "factor": "oxygen_saturation",
                    "value": f"{spo2}%",
                    "risk_level": "moderate",
                    "description": "Low oxygen saturation"
                })
    
    # Past medical history risks
    if ehr_data and ehr_data.get('pmh'):
        pmh = ehr_data['pmh']
        for condition in pmh:
            condition_lower = condition.lower()
            if any(term in condition_lower for term in ['diabetes', 'hypertension', 'heart', 'stroke']):
                risk_factors.append({
                    "factor": "past_medical_history",
                    "value": condition,
                    "risk_level": "high",
                    "description": f"History of {condition} increases risk for related complications"
                })
    
    # Social history risks
    if ehr_data and ehr_data.get('social'):
        social = ehr_data['social']
        
        if social.get('tobacco') in ['current', 'former']:
            risk_factors.append({
                "factor": "tobacco_use",
                "value": social['tobacco'],
                "risk_level": "high",
                "description": "Tobacco use significantly increases cardiovascular and pulmonary risks"
            })
        
        if social.get('alcohol') in ['heavy', 'excessive']:
            risk_factors.append({
                "factor": "alcohol_use",
                "value": social['alcohol'],
                "risk_level": "moderate",
                "description": "Heavy alcohol use increases multiple health risks"
            })
    
    return risk_factors

def generate_red_flag_alerts(
    extraction: Dict[str, Any],
    ehr_data: Optional[Dict[str, Any]] = None,
    fusion_results: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Generate red flag alerts based on clinical data
    """
    alerts = []
    
    # Check for critical vital signs
    if ehr_data and ehr_data.get('vital_signs'):
        vs = ehr_data['vital_signs']
        
        # Hypertensive crisis
        bp = vs.get('bp')
        if bp:
            bp_match = re.search(r'(\d+)/(\d+)', str(bp))
            if bp_match:
                systolic = int(bp_match.group(1))
                diastolic = int(bp_match.group(2))
                
                if systolic >= 180 or diastolic >= 110:
                    alerts.append({
                        "alert_type": "critical",
                        "condition": "hypertensive_crisis",
                        "urgency": "immediate",
                        "message": f"Blood pressure {bp} indicates hypertensive crisis - immediate attention required",
                        "action_required": "Consider emergency evaluation and antihypertensive treatment",
                        "time_sensitivity": "within 1 hour"
                    })
        
        # Severe tachycardia
        hr = vs.get('hr')
        if hr and hr > 120:
            alerts.append({
                "alert_type": "urgent",
                "condition": "severe_tachycardia",
                "urgency": "urgent",
                "message": f"Heart rate {hr} bpm indicates severe tachycardia",
                "action_required": "ECG and cardiac evaluation recommended",
                "time_sensitivity": "within 2 hours"
            })
        
        # Hypoxia
        spo2 = vs.get('spo2_pct')
        if spo2 and spo2 < 90:
            alerts.append({
                "alert_type": "critical",
                "condition": "hypoxia",
                "urgency": "immediate",
                "message": f"Oxygen saturation {spo2}% indicates severe hypoxia",
                "action_required": "Immediate oxygen therapy and respiratory evaluation",
                "time_sensitivity": "immediate"
            })
        
        # High fever
        temp = vs.get('temp_f')
        if temp and temp > 103:
            alerts.append({
                "alert_type": "urgent",
                "condition": "high_fever",
                "urgency": "urgent",
                "message": f"Temperature {temp}°F indicates high fever",
                "action_required": "Fever workup and antipyretic treatment",
                "time_sensitivity": "within 4 hours"
            })
    
    # Check symptoms for red flags
    if extraction and extraction.get('extracted'):
        extracted = extraction['extracted']
        symptoms = extracted.get('symptoms', [])
        
        for symptom in symptoms:
            symptom_lower = symptom.lower()
            
            # Chest pain red flags
            if 'chest pain' in symptom_lower:
                if any(term in symptom_lower for term in ['crushing', 'severe', 'radiating', 'pressure']):
                    alerts.append({
                        "alert_type": "critical",
                        "condition": "acute_coronary_syndrome",
                        "urgency": "immediate",
                        "message": "Severe chest pain with concerning features - rule out acute coronary syndrome",
                        "action_required": "Immediate ECG, cardiac enzymes, and cardiology consultation",
                        "time_sensitivity": "immediate"
                    })
            
            # Neurological red flags
            if any(term in symptom_lower for term in ['stroke', 'paralysis', 'numbness', 'weakness']):
                alerts.append({
                    "alert_type": "critical",
                    "condition": "stroke_suspected",
                    "urgency": "immediate",
                    "message": "Neurological symptoms suggest possible stroke - immediate attention required",
                    "action_required": "Immediate neurological evaluation and stroke protocol activation",
                    "time_sensitivity": "immediate"
                })
            
            # Respiratory red flags
            if any(term in symptom_lower for term in ['shortness of breath', 'difficulty breathing', 'chest tightness']):
                if 'severe' in symptom_lower or 'can\'t breathe' in symptom_lower:
                    alerts.append({
                        "alert_type": "critical",
                        "condition": "respiratory_distress",
                        "urgency": "immediate",
                        "message": "Severe respiratory symptoms - immediate evaluation required",
                        "action_required": "Immediate respiratory assessment and oxygen therapy",
                        "time_sensitivity": "immediate"
                    })
    
    # Check fusion results for high-risk conditions
    if fusion_results:
        for result in fusion_results[:3]:  # Check top 3
            condition = result.get('condition', '')
            score = result.get('score', 0.0)
            
            # High-risk conditions that need immediate attention
            critical_conditions = [
                'acute_coronary_syndrome_suspected',
                'stroke_suspected',
                'pulmonary_embolism_suspected',
                'aortic_emergency_red_flags',
                'pneumothorax_red_flags'
            ]
            
            if condition in critical_conditions and score > 0.7:
                alerts.append({
                    "alert_type": "critical",
                    "condition": condition,
                    "urgency": "immediate",
                    "message": f"High probability of {condition.replace('_', ' ')} - immediate evaluation required",
                    "action_required": "Immediate specialist consultation and diagnostic workup",
                    "time_sensitivity": "immediate"
                })
    
    return alerts
