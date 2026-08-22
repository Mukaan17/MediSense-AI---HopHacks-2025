# -*- coding: utf-8 -*-
"""Structured clinical diagnosis, split by concern:

    differential.py  LLM structured differential + validation/cleaning
    risk.py          deterministic risk-factor and red-flag rules
    summary.py       brief working-diagnosis summary

`core.clinical_diagnosis` remains as a compatibility shim over this package.
"""

from .differential import generate_structured_differential_diagnosis
from .risk import analyze_risk_factors, generate_red_flag_alerts
from .summary import generate_brief_diagnosis_summary

__all__ = [
    "generate_structured_differential_diagnosis",
    "analyze_risk_factors",
    "generate_red_flag_alerts",
    "generate_brief_diagnosis_summary",
]
