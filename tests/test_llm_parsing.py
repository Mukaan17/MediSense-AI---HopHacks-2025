"""Golden-fixture tests for the consolidated LLM JSON salvage parser.

Fixtures mirror shapes real models actually emit: clean JSON, fenced
markdown, prose-wrapped objects, trailing junk, and unrecoverable output.
"""

from core.utils import json_sanitize, parse_llm_json

DEFAULT = {"questions": []}


def test_plain_json_object():
    out = parse_llm_json('{"questions": [{"q": "Any fever?"}]}', DEFAULT)
    assert out["questions"][0]["q"] == "Any fever?"


def test_json_fenced_block():
    text = '```json\n{"questions": [{"q": "Chest pain on exertion?"}]}\n```'
    out = parse_llm_json(text, DEFAULT)
    assert out["questions"][0]["q"] == "Chest pain on exertion?"


def test_bare_fenced_block():
    text = '```\n{"summary": "stable"}\n```'
    assert parse_llm_json(text, DEFAULT) == {"summary": "stable"}


def test_prose_wrapped_object():
    text = (
        "Sure! Here is the structured result you asked for:\n\n"
        '{"differential_diagnosis": {"top_3_diagnoses": []}, "citations": []}\n\n'
        "Let me know if you need anything else."
    )
    out = parse_llm_json(text, DEFAULT)
    assert "differential_diagnosis" in out


def test_fence_with_surrounding_prose():
    text = (
        "The analysis follows.\n"
        '```json\n{"potential_issues_ranked": [{"condition": "asthma_exacerbation"}]}\n```\n'
        "Advisory only."
    )
    out = parse_llm_json(text, DEFAULT)
    assert out["potential_issues_ranked"][0]["condition"] == "asthma_exacerbation"


def test_trailing_junk_after_object():
    out = parse_llm_json('{"a": 1} trailing tokens the model kept generating', DEFAULT)
    assert out == {"a": 1}


def test_braces_inside_string_values():
    out = parse_llm_json('Result: {"note": "use {caution}"} done', DEFAULT)
    assert out == {"note": "use {caution}"}


def test_truncated_json_returns_default():
    assert parse_llm_json('{"questions": [{"q": "incomplete', DEFAULT) is DEFAULT


def test_no_object_returns_default():
    assert parse_llm_json("I cannot produce JSON for this request.", DEFAULT) is DEFAULT


def test_empty_and_none_return_default():
    assert parse_llm_json("", DEFAULT) is DEFAULT
    assert parse_llm_json(None, DEFAULT) is DEFAULT


def test_non_dict_json_returns_default():
    assert parse_llm_json('["a", "b"]', DEFAULT) is DEFAULT
    assert parse_llm_json("42", DEFAULT) is DEFAULT


def test_json_sanitize_alias():
    assert json_sanitize('{"x": 1}', DEFAULT) == {"x": 1}
    assert json_sanitize("garbage", DEFAULT) is DEFAULT


def test_fence_wins_over_unbalanced_brace_noise():
    # The widest {...} span is unparseable here, so only the fence path can
    # recover the object (kills mutants that break the fence regex).
    text = 'note { broken\n```json\n{"a": 1}\n```\ntail'
    assert parse_llm_json(text, DEFAULT) == {"a": 1}


def test_clamp_confidence_bounds():
    from core.utils import clamp_confidence
    assert clamp_confidence("not a number") == 0.0
    assert clamp_confidence(-3) == 0.0
    assert clamp_confidence(1.7) == 1.0
    assert clamp_confidence("0.5") == 0.5


def test_top_n_bounds():
    from core.utils import top_n
    assert top_n([1, 2, 3], 2) == [1, 2]
    assert top_n([1, 2, 3], 0) == []
    assert top_n([1, 2, 3], -1) == []
