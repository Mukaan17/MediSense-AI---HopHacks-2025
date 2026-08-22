"""Prompt templates render with real Jinja2 semantics (StrictUndefined)."""

import pytest
from jinja2 import UndefinedError

from core.config import render_prompt


def test_answer_template_renders_all_variables():
    out = render_prompt(
        "answer",
        allowed_labels="asthma_exacerbation, pneumonia_unspecified",
        extraction='{"chief_complaint": "cough"}',
        context="doc snippet",
    )
    assert "asthma_exacerbation" in out
    assert '"chief_complaint": "cough"' in out
    assert "doc snippet" in out
    assert "{{" not in out


def test_structured_diagnosis_template_renders_all_variables():
    out = render_prompt(
        "structured_diagnosis",
        allowed_labels="heart_failure_exacerbation",
        extraction='{"symptoms": ["edema"]}',
        context="retrieved context",
        ehr_context="EHR Patient ID: MIMIC_1",
        fusion_context="1. heart_failure_exacerbation (0.80)",
    )
    assert "heart_failure_exacerbation" in out
    assert "EHR Patient ID: MIMIC_1" in out
    assert "{{" not in out


def test_missing_variable_fails_loudly():
    with pytest.raises(UndefinedError):
        render_prompt("answer", allowed_labels="x", extraction="{}")
