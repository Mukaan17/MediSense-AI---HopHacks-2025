from core.extract import extractor_generate
from core.questioner_llm import is_prescriptive, parse_bullet_questions


def test_extractor_finds_symptoms_and_vitals():
    conversation = (
        "patient: I have had a bad cough and fever for three days. "
        "My blood pressure was 145/92 this morning. I am taking lisinopril."
    )
    out = extractor_generate(conversation)
    extracted = out["extracted"]
    symptoms = " ".join(extracted.get("symptoms", []))
    assert "cough" in symptoms
    assert "fever" in symptoms
    assert out["retrieval_query"], "retrieval query must be synthesized"


def test_extractor_negation():
    out = extractor_generate("patient: I have a cough but no fever and denies chest pain.")
    negated = " ".join(out["extracted"].get("negated_findings", []))
    assert "fever" in negated or "chest pain" in negated


def test_prescriptive_filter():
    assert is_prescriptive("Take 50 mg of aspirin")
    assert is_prescriptive("Should we prescribe antibiotics?")
    assert not is_prescriptive("Any recent travel or sick contacts?")


def test_parse_bullet_questions_filters_and_caps():
    text = (
        "- Any recent travel or sick contacts?\n"
        "* Take 500 mg of amoxicillin now\n"
        "- Is the cough producing sputum?\n"
        "- Any night sweats?\n"
        "- Any weight loss?\n"
    )
    qs = parse_bullet_questions(text, max_questions=3)
    texts = [q["q"] for q in qs]
    assert len(qs) == 3
    assert all(not is_prescriptive(t) for t in texts)
    assert "Any recent travel or sick contacts?" in texts
