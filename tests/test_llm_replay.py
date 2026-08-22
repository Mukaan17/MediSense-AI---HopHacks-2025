"""Record/replay contract tests: fixture LLM responses (recorded or
hand-authored in recorded shape) flow through the real post-processing, so
a prompt-contract or parsing regression fails here without live keys.

Refresh fixtures with real responses: scripts/record_llm_fixtures.py.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"


def _fixture(name: str) -> str:
    return json.loads((FIXTURES / name).read_text())["response"]


class _StubLLM:
    def __init__(self, response: str):
        self._response = response

    def invoke(self, _prompt):
        class R:
            content = self._response
        return R()

    def invoke_json(self, _prompt):
        return self.invoke(_prompt)


def test_questioner_replay_filters_and_orders(monkeypatch):
    from core import questioner_llm

    monkeypatch.setattr(questioner_llm, "get_llm",
                        lambda **kw: _StubLLM(_fixture("questioner_response.json")))
    out = questioner_llm.propose_questions_llm({"top_candidates": []}, max_questions=4)
    # The prescriptive dosing question must be filtered; the rest survive.
    assert len(out) == 2
    texts = [q["q"] for q in out]
    assert all("amoxicillin" not in t for t in texts)
    # Fixture's red-flag question survives with its priority intact.
    assert any(q["priority"] == "red-flag" for q in out)


def test_answer_replay_enforces_closed_set_and_clamps(monkeypatch):
    from core import answer

    monkeypatch.setattr(answer, "get_llm",
                        lambda **kw: _StubLLM(_fixture("answer_response.json")))
    out = answer.answerer_generate({"extracted": {}}, "ctx")
    conditions = [i["condition"] for i in out["potential_issues_ranked"]]
    assert "made_up_condition_xyz" not in conditions  # closed set enforced
    assert all(0.0 <= i["confidence"] <= 1.0 for i in out["potential_issues_ranked"])
    assert out["citations"] == ["English Train.json §item_5.c1"]


def test_structured_diagnosis_replay_survives_prose_wrap(monkeypatch):
    from core.diagnosis import differential

    monkeypatch.setattr(differential, "get_llm",
                        lambda **kw: _StubLLM(_fixture("structured_diagnosis_response.json")))
    out = differential.generate_structured_differential_diagnosis({"extracted": {}}, "ctx")
    top = out["differential_diagnosis"]["top_3_diagnoses"]
    assert top and top[0]["condition"] == "pneumonia_unspecified"
    assert out["clinical_workflow"]["order_suggestions"] == ["CBC"]


def test_coach_stream_replay_parses_tags_and_filters():
    from core.questioner_llm import parse_bullet_questions

    out = parse_bullet_questions(_fixture("coach_stream_response.json"), max_questions=3)
    # Red flag sorts first; the prescriptive aspirin line is filtered.
    assert out[0]["priority"] == "red-flag"
    assert all("aspirin" not in q["q"].lower() for q in out)


def test_claude_calls_carry_cache_breakpoints():
    # Structural check: system prompts go up as content blocks with a cache
    # breakpoint, so long stable prompts cache without further code change.
    from core.llm_client import _system_blocks

    blocks = _system_blocks("stable system prompt")
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["text"] == "stable system prompt"
