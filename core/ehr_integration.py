"""
EHR Integration Module
Provides clinical workflow integration features for EHR/EMR systems
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

def generate_ehr_workflow_actions(
    diagnosis_result: Dict[str, Any],
    ehr_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate EHR workflow actions based on diagnosis results
    """
    workflow = {
        "ehr_actions": [],
        "order_suggestions": [],
        "follow_up_plan": [],
        "documentation_notes": []
    }
    
    # Extract diagnosis information
    dd = diagnosis_result.get("differential_diagnosis", {})
    top_diagnoses = dd.get("top_3_diagnoses", [])
    red_flags = dd.get("red_flag_alerts", [])
    risk_assessment = dd.get("risk_assessment", {})
    
    # Generate EHR actions based on top diagnoses
    for diagnosis in top_diagnoses:
        condition = diagnosis.get("condition", "")
        confidence = diagnosis.get("confidence", 0.0)
        
        if confidence > 0.7:  # High confidence diagnoses
            workflow["ehr_actions"].append({
                "action": "add_to_problem_list",
                "condition": condition,
                "priority": "high",
                "icd10_code": _get_icd10_code(condition),
                "confidence": confidence,
                "reasoning": f"High confidence diagnosis based on clinical evidence"
            })
            
            # Add medication alerts if applicable
            if _requires_medication_alert(condition):
                workflow["ehr_actions"].append({
                    "action": "create_alert",
                    "type": "medication_interaction",
                    "message": f"Consider medication adjustments for {condition.replace('_', ' ')}",
                    "priority": "moderate"
                })
    
    # Generate order suggestions based on diagnoses and red flags
    workflow["order_suggestions"] = _generate_order_suggestions(top_diagnoses, red_flags, ehr_data)
    
    # Generate follow-up plan
    workflow["follow_up_plan"] = _generate_follow_up_plan(top_diagnoses, risk_assessment, ehr_data)
    
    # Generate documentation notes
    workflow["documentation_notes"] = _generate_documentation_notes(diagnosis_result, ehr_data)
    
    return workflow

def _get_icd10_code(condition: str) -> str:
    """Map conditions to ICD-10 codes"""
    icd10_mapping = {
        "hypertension_uncontrolled": "I10",
        "heart_failure_exacerbation": "I50.9",
        "atrial_fibrillation_suspected": "I48.91",
        "acute_coronary_syndrome_suspected": "I25.9",
        "pneumonia_unspecified": "J18.9",
        "copd_exacerbation": "J44.1",
        "asthma_exacerbation": "J45.901",
        "type_2_diabetes_hyperglycemia": "E11.9",
        "urinary_tract_infection": "N39.0",
        "gastroesophageal_reflux": "K21.9",
        "migraine": "G43.909",
        "depressive_symptoms": "F32.9",
        "generalized_anxiety": "F41.9",
        "stroke_suspected": "I63.9",
        "pulmonary_embolism_suspected": "I26.9"
    }
    return icd10_mapping.get(condition, "")

def _requires_medication_alert(condition: str) -> bool:
    """Check if condition requires medication alerts"""
    medication_conditions = [
        "hypertension_uncontrolled",
        "heart_failure_exacerbation",
        "type_2_diabetes_hyperglycemia",
        "copd_exacerbation",
        "asthma_exacerbation"
    ]
    return condition in medication_conditions

def _generate_order_suggestions(
    diagnoses: List[Dict[str, Any]], 
    red_flags: List[Dict[str, Any]],
    ehr_data: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Generate laboratory and imaging order suggestions"""
    orders = []
    
    # Orders based on diagnoses
    for diagnosis in diagnoses:
        condition = diagnosis.get("condition", "")
        confidence = diagnosis.get("confidence", 0.0)
        
        if confidence > 0.6:  # Moderate to high confidence
            if condition == "hypertension_uncontrolled":
                orders.extend([
                    {
                        "order_type": "lab",
                        "test": "Basic Metabolic Panel",
                        "urgency": "routine",
                        "reasoning": "Baseline renal function before antihypertensive adjustment"
                    },
                    {
                        "order_type": "imaging",
                        "test": "ECG",
                        "urgency": "routine",
                        "reasoning": "Rule out cardiac complications of hypertension"
                    }
                ])
            
            elif condition == "heart_failure_exacerbation":
                orders.extend([
                    {
                        "order_type": "lab",
                        "test": "BNP or NT-proBNP",
                        "urgency": "urgent",
                        "reasoning": "Confirm heart failure diagnosis and assess severity"
                    },
                    {
                        "order_type": "imaging",
                        "test": "Chest X-ray",
                        "urgency": "urgent",
                        "reasoning": "Assess pulmonary congestion and cardiac size"
                    },
                    {
                        "order_type": "lab",
                        "test": "Basic Metabolic Panel",
                        "urgency": "urgent",
                        "reasoning": "Monitor electrolytes, especially potassium and creatinine"
                    }
                ])
            
            elif condition == "pneumonia_unspecified":
                orders.extend([
                    {
                        "order_type": "imaging",
                        "test": "Chest X-ray",
                        "urgency": "urgent",
                        "reasoning": "Confirm pneumonia diagnosis and assess extent"
                    },
                    {
                        "order_type": "lab",
                        "test": "Complete Blood Count",
                        "urgency": "urgent",
                        "reasoning": "Assess for infection and inflammatory response"
                    },
                    {
                        "order_type": "lab",
                        "test": "Blood Cultures",
                        "urgency": "routine",
                        "reasoning": "Identify causative organism if severe"
                    }
                ])
            
            elif condition == "type_2_diabetes_hyperglycemia":
                orders.extend([
                    {
                        "order_type": "lab",
                        "test": "Hemoglobin A1C",
                        "urgency": "routine",
                        "reasoning": "Assess long-term glucose control"
                    },
                    {
                        "order_type": "lab",
                        "test": "Basic Metabolic Panel",
                        "urgency": "routine",
                        "reasoning": "Monitor glucose, electrolytes, and renal function"
                    }
                ])
    
    # Orders based on red flags
    for alert in red_flags:
        alert_type = alert.get("alert_type", "")
        condition = alert.get("condition", "")
        
        if alert_type == "critical":
            if "hypertensive_crisis" in condition:
                orders.append({
                    "order_type": "imaging",
                    "test": "ECG",
                    "urgency": "stat",
                    "reasoning": "Rule out cardiac complications of hypertensive crisis"
                })
            
            elif "stroke" in condition:
                orders.extend([
                    {
                        "order_type": "imaging",
                    "test": "CT Head",
                        "urgency": "stat",
                        "reasoning": "Rule out acute stroke or hemorrhage"
                    },
                    {
                        "order_type": "lab",
                        "test": "Complete Blood Count",
                        "urgency": "stat",
                        "reasoning": "Baseline labs for stroke workup"
                    }
                ])
            
            elif "acute_coronary" in condition:
                orders.extend([
                    {
                        "order_type": "imaging",
                        "test": "ECG",
                        "urgency": "stat",
                        "reasoning": "Rule out acute coronary syndrome"
                    },
                    {
                        "order_type": "lab",
                        "test": "Troponin",
                        "urgency": "stat",
                        "reasoning": "Rule out myocardial infarction"
                    }
                ])
    
    # Remove duplicates and prioritize by urgency
    unique_orders = []
    seen = set()
    for order in orders:
        key = (order["order_type"], order["test"])
        if key not in seen:
            unique_orders.append(order)
            seen.add(key)
    
    # Sort by urgency
    urgency_order = {"stat": 0, "urgent": 1, "routine": 2}
    unique_orders.sort(key=lambda x: urgency_order.get(x["urgency"], 3))
    
    return unique_orders

def _generate_follow_up_plan(
    diagnoses: List[Dict[str, Any]],
    risk_assessment: Dict[str, Any],
    ehr_data: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Generate follow-up plan based on diagnoses and risk assessment"""
    follow_ups = []
    
    overall_risk = risk_assessment.get("overall_risk_level", "unknown")
    
    # Follow-up based on top diagnosis
    if diagnoses:
        top_diagnosis = diagnoses[0]
        condition = top_diagnosis.get("condition", "")
        confidence = top_diagnosis.get("confidence", 0.0)
        
        if confidence > 0.7:
            if condition == "hypertension_uncontrolled":
                follow_ups.append({
                    "timeline": "1 week",
                    "reason": "Monitor blood pressure response to treatment",
                    "actions": [
                        "Blood pressure recheck",
                        "Assess medication adherence",
                        "Review lifestyle modifications"
                    ]
                })
            
            elif condition == "heart_failure_exacerbation":
                follow_ups.append({
                    "timeline": "3-5 days",
                    "reason": "Monitor heart failure symptoms and medication response",
                    "actions": [
                        "Weight monitoring",
                        "Symptom assessment",
                        "Medication adjustment if needed"
                    ]
                })
            
            elif condition == "pneumonia_unspecified":
                follow_ups.append({
                    "timeline": "48-72 hours",
                    "reason": "Monitor pneumonia response to treatment",
                    "actions": [
                        "Symptom improvement assessment",
                        "Temperature monitoring",
                        "Consider antibiotic adjustment if no improvement"
                    ]
                })
    
    # Follow-up based on risk level
    if overall_risk in ["critical", "high"]:
        follow_ups.append({
            "timeline": "24-48 hours",
            "reason": "High-risk patient requires close monitoring",
            "actions": [
                "Vital signs monitoring",
                "Symptom assessment",
                "Consider specialist consultation"
            ]
        })
    
    # Follow-up based on age and comorbidities
    if ehr_data:
        age = ehr_data.get("age")
        pmh = ehr_data.get("pmh", [])
        
        if age and age >= 65:
            follow_ups.append({
                "timeline": "2 weeks",
                "reason": "Geriatric patient with multiple comorbidities",
                "actions": [
                    "Comprehensive medication review",
                    "Fall risk assessment",
                    "Cognitive screening if indicated"
                ]
            })
    
    return follow_ups

def _generate_documentation_notes(
    diagnosis_result: Dict[str, Any],
    ehr_data: Optional[Dict[str, Any]]
) -> List[str]:
    """Generate clinical documentation notes"""
    notes = []
    
    dd = diagnosis_result.get("differential_diagnosis", {})
    top_diagnoses = dd.get("top_3_diagnoses", [])
    red_flags = dd.get("red_flag_alerts", [])
    
    # Document top diagnoses
    if top_diagnoses:
        notes.append("Differential Diagnosis:")
        for i, diagnosis in enumerate(top_diagnoses, 1):
            condition = diagnosis.get("condition", "").replace("_", " ").title()
            confidence = diagnosis.get("confidence", 0.0)
            likelihood = diagnosis.get("likelihood", "unknown")
            notes.append(f"{i}. {condition} (confidence: {confidence:.2f}, likelihood: {likelihood})")
    
    # Document red flags
    if red_flags:
        notes.append("\nRed Flag Alerts:")
        for alert in red_flags:
            alert_type = alert.get("alert_type", "").upper()
            message = alert.get("message", "")
            notes.append(f"- {alert_type}: {message}")
    
    # Document clinical reasoning
    if top_diagnoses:
        notes.append("\nClinical Reasoning:")
        for diagnosis in top_diagnoses:
            supporting_evidence = diagnosis.get("supporting_evidence", [])
            if supporting_evidence:
                condition = diagnosis.get("condition", "").replace("_", " ").title()
                notes.append(f"- {condition}: {', '.join(supporting_evidence)}")
    
    # Document next steps
    if top_diagnoses:
        notes.append("\nNext Steps:")
        for diagnosis in top_diagnoses:
            next_steps = diagnosis.get("next_steps", [])
            if next_steps:
                condition = diagnosis.get("condition", "").replace("_", " ").title()
                notes.append(f"- {condition}: {', '.join(next_steps)}")
    
    return notes

def create_ehr_integration_summary(
    diagnosis_result: Dict[str, Any],
    ehr_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a comprehensive EHR integration summary
    """
    workflow = generate_ehr_workflow_actions(diagnosis_result, ehr_data)
    
    return {
        "patient_summary": {
            "patient_id": ehr_data.get("patient_id") if ehr_data else None,
            "demographics": {
                "age": ehr_data.get("age") if ehr_data else None,
                "sex": ehr_data.get("sex") if ehr_data else None
            },
            "vital_signs": ehr_data.get("vital_signs") if ehr_data else None,
            "current_medications": ehr_data.get("meds", []) if ehr_data else [],
            "allergies": ehr_data.get("allergies", []) if ehr_data else []
        },
        "clinical_assessment": diagnosis_result.get("differential_diagnosis", {}),
        "workflow_actions": workflow,
        "integration_timestamp": datetime.now().isoformat(),
        "ehr_system": "Epic",  # Could be made configurable
        "integration_status": "ready_for_import"
    }
