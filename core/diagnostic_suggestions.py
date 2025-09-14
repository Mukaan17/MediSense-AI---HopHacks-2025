# -*- coding: utf-8 -*-
"""
Enhanced diagnostic suggestions module for clinician coaching
Provides intelligent suggestions to boost RAG confidence and guide diagnosis
"""

import json
import os
from typing import Dict, Any, List, Optional
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage

# Configuration
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

def _llm():
    """Initialize the LLM client"""
    return ChatGroq(model=GROQ_MODEL, temperature=TEMPERATURE)

SYSTEM_PROMPT = (
    "You are an expert clinical decision support system specializing in chest imaging and respiratory conditions. "
    "Your role is to provide intelligent diagnostic suggestions that help clinicians: "
    "1) Increase diagnostic confidence through targeted questioning "
    "2) Identify key symptoms that differentiate between conditions "
    "3) Recognize red flags and urgent findings "
    "4) Guide clinical reasoning for better patient outcomes. "
    "You must return STRICT JSON only."
)

DIAGNOSTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnostic_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["key_symptom", "differential", "confidence_boost", "red_flag"]},
                    "suggestion": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                },
                "required": ["type", "suggestion", "reasoning", "priority"]
            }
        },
        "confidence_analysis": {
            "type": "object",
            "properties": {
                "factors": {"type": "array", "items": {"type": "string"}},
                "missing_info": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["factors", "missing_info", "recommendations"]
        },
        "clinical_reasoning": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["diagnostic_suggestions", "confidence_analysis", "clinical_reasoning"]
}

PROMPT_TEMPLATE = """Analyze the current case state and provide enhanced diagnostic suggestions.

CASE STATE:
{state}

GOALS:
1. Generate diagnostic suggestions that will increase confidence in the leading diagnosis
2. Identify key symptoms or findings that would help differentiate between conditions
3. Highlight any red flags or urgent considerations
4. Provide clinical reasoning to guide the diagnostic process
5. Analyze confidence factors and identify missing information

CONSTRAINTS:
- Focus on chest/respiratory conditions as primary scope
- Prioritize patient safety and red flags
- Keep suggestions concise and actionable
- Base recommendations on evidence-based medicine
- Consider both imaging and clinical findings

RETURN STRICT JSON matching this schema:
{schema}"""

def generate_diagnostic_suggestions(
    state: Dict[str, Any],
    max_suggestions: int = 5
) -> Dict[str, Any]:
    """
    Generate enhanced diagnostic suggestions based on current case state
    
    Args:
        state: Current case state including findings, confidence, context
        max_suggestions: Maximum number of suggestions to generate
        
    Returns:
        Dictionary containing diagnostic suggestions, confidence analysis, and clinical reasoning
    """
    try:
        lm = _llm()
        
        # Prepare the state for analysis
        analysis_state = {
            "top_candidates": state.get("top_candidates", [])[:5],
            "current_confidence": state.get("top_confidence", 0.0),
            "confidence_margin": state.get("margin", 0.0),
            "image_findings": state.get("image_findings", []),
            "text_findings": state.get("text_findings", []),
            "ehr_summary": state.get("ehr_summary", {}),
            "extracted_symptoms": state.get("extraction", {}),
            "retrieved_context": state.get("retrieved_context", ""),
            "max_suggestions": max_suggestions
        }
        
        prompt = PROMPT_TEMPLATE.format(
            schema=json.dumps(DIAGNOSTIC_SCHEMA, indent=2),
            state=json.dumps(analysis_state, ensure_ascii=False)
        )
        
        response = lm([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]).content.strip()
        
        # Parse JSON response with fallback
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                data = _generate_fallback_suggestions(state)
        
        # Validate and clean the response
        return _validate_and_clean_suggestions(data, state)
        
    except Exception as e:
        print(f"Error generating diagnostic suggestions: {e}")
        return _generate_fallback_suggestions(state)

def _validate_and_clean_suggestions(data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean the diagnostic suggestions response"""
    
    # Ensure required fields exist
    result = {
        "diagnostic_suggestions": [],
        "confidence_analysis": {
            "factors": [],
            "missing_info": [],
            "recommendations": []
        },
        "clinical_reasoning": []
    }
    
    # Process diagnostic suggestions
    suggestions = data.get("diagnostic_suggestions", [])
    for suggestion in suggestions[:5]:  # Limit to 5 suggestions
        if isinstance(suggestion, dict):
            clean_suggestion = {
                "type": suggestion.get("type", "confidence_boost"),
                "suggestion": suggestion.get("suggestion", ""),
                "reasoning": suggestion.get("reasoning", ""),
                "priority": suggestion.get("priority", "medium")
            }
            
            # Validate suggestion content
            if clean_suggestion["suggestion"] and len(clean_suggestion["suggestion"]) > 10:
                result["diagnostic_suggestions"].append(clean_suggestion)
    
    # Process confidence analysis
    confidence_analysis = data.get("confidence_analysis", {})
    if isinstance(confidence_analysis, dict):
        result["confidence_analysis"]["factors"] = confidence_analysis.get("factors", [])[:5]
        result["confidence_analysis"]["missing_info"] = confidence_analysis.get("missing_info", [])[:5]
        result["confidence_analysis"]["recommendations"] = confidence_analysis.get("recommendations", [])[:3]
    
    # Process clinical reasoning
    clinical_reasoning = data.get("clinical_reasoning", [])
    if isinstance(clinical_reasoning, list):
        result["clinical_reasoning"] = clinical_reasoning[:4]
    
    return result

def _generate_fallback_suggestions(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate fallback suggestions when LLM fails"""
    
    top_candidates = state.get("top_candidates", [])
    current_confidence = state.get("top_confidence", 0.0)
    confidence_margin = state.get("margin", 0.0)
    
    suggestions = []
    
    # Generate suggestions based on confidence level
    if current_confidence < 0.7:
        suggestions.append({
            "type": "confidence_boost",
            "suggestion": "Ask about specific symptoms that would support the leading diagnosis",
            "reasoning": "Low confidence suggests need for more specific symptom information",
            "priority": "high"
        })
    
    if confidence_margin < 0.1 and len(top_candidates) > 1:
        suggestions.append({
            "type": "differential",
            "suggestion": "Focus on symptoms that differentiate between top 2-3 conditions",
            "reasoning": "Close confidence scores indicate need for better differentiation",
            "priority": "high"
        })
    
    # Add generic suggestions
    if not suggestions:
        suggestions.append({
            "type": "key_symptom",
            "suggestion": "Explore additional symptoms and their duration/severity",
            "reasoning": "More symptom details can improve diagnostic accuracy",
            "priority": "medium"
        })
    
    return {
        "diagnostic_suggestions": suggestions,
        "confidence_analysis": {
            "factors": ["Current imaging findings", "Patient history"],
            "missing_info": ["Detailed symptom timeline", "Associated symptoms"],
            "recommendations": ["Continue systematic questioning", "Consider additional imaging if needed"]
        },
        "clinical_reasoning": [
            "Systematic approach to symptom evaluation",
            "Consider differential diagnoses based on findings"
        ]
    }

def analyze_confidence_factors(
    ranked_candidates: List[Dict[str, Any]],
    current_confidence: float,
    margin: float
) -> Dict[str, Any]:
    """
    Analyze factors affecting diagnostic confidence
    
    Args:
        ranked_candidates: List of ranked diagnostic candidates
        current_confidence: Current confidence score
        margin: Confidence margin between top candidates
        
    Returns:
        Analysis of confidence factors
    """
    factors = []
    missing_info = []
    recommendations = []
    
    # Analyze confidence level
    if current_confidence < 0.6:
        factors.append("Low overall confidence - multiple possibilities")
        missing_info.append("Key differentiating symptoms")
        recommendations.append("Focus on high-yield questions")
    elif current_confidence < 0.8:
        factors.append("Moderate confidence with some uncertainty")
        missing_info.append("Supporting evidence for leading diagnosis")
        recommendations.append("Seek confirmatory findings")
    else:
        factors.append("High confidence in leading diagnosis")
        recommendations.append("Consider ruling out key differentials")
    
    # Analyze margin
    if margin < 0.1:
        factors.append("Close competition between top candidates")
        missing_info.append("Clear differentiating criteria")
        recommendations.append("Focus on distinguishing features")
    
    # Analyze number of candidates
    if len(ranked_candidates) > 3:
        factors.append("Multiple diagnostic possibilities")
        missing_info.append("Narrowing criteria")
        recommendations.append("Prioritize most likely diagnoses")
    
    return {
        "factors": factors,
        "missing_info": missing_info,
        "recommendations": recommendations
    }
