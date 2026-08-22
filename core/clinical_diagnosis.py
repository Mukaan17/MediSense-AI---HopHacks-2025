# -*- coding: utf-8 -*-
"""Compatibility shim: the implementation lives in the `core.diagnosis`
package (differential / risk / summary). Import from there in new code."""

from .diagnosis import (
    analyze_risk_factors,
    generate_brief_diagnosis_summary,
    generate_red_flag_alerts,
    generate_structured_differential_diagnosis,
)

__all__ = [
    "generate_structured_differential_diagnosis",
    "analyze_risk_factors",
    "generate_red_flag_alerts",
    "generate_brief_diagnosis_summary",
]
