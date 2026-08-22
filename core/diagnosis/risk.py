# -*- coding: utf-8 -*-
"""Deterministic risk-factor analysis and red-flag alert rules."""

import re
from typing import Any, Dict, List, Optional


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
