"""Property-based tests (hypothesis): the parsers and chunkers must hold
their invariants for arbitrary input, not just the fixtures we thought of."""

import json

from hypothesis import given, settings, strategies as st

from core.utils import parse_llm_json
from core.extract import extractor_generate
from rag_runtime.chunking import chunk_words, chunk_dialogue

DEFAULT = {"questions": []}

json_objects = st.dictionaries(
    st.text(min_size=1, max_size=8),
    st.recursive(
        st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False),
                  st.text(max_size=20)),
        lambda children: st.lists(children, max_size=3),
        max_leaves=8,
    ),
    max_size=4,
)


@settings(max_examples=60, deadline=None)
@given(st.text(max_size=400))
def test_parse_llm_json_never_raises(text):
    out = parse_llm_json(text, DEFAULT)
    assert isinstance(out, dict)


@settings(max_examples=40, deadline=None)
@given(json_objects, st.text(max_size=40), st.text(max_size=40))
def test_parse_llm_json_recovers_embedded_object(obj, prefix, suffix):
    # An intact JSON object embedded in prose must be recovered whenever the
    # surrounding noise carries no braces (or backticks) of its own.
    noise = prefix + suffix
    if any(ch in noise for ch in "{}`"):
        return
    text = f"{prefix}{json.dumps(obj)}{suffix}"
    assert parse_llm_json(text, DEFAULT) == obj


@settings(max_examples=40, deadline=None)
@given(st.lists(st.sampled_from("alpha beta gamma delta cough fever".split()),
                min_size=0, max_size=200))
def test_chunk_words_window_and_coverage(words):
    text = " ".join(words)
    # Precondition of the coverage guarantee: overlap >= MIN_CHUNK_WORDS,
    # so a dropped short tail is always inside the previous window's
    # overlap (holds for the production defaults 180/40).
    chunks = chunk_words(text, max_words=30, overlap=15)
    for c in chunks:
        assert len(c.split()) <= 30
    covered = set()
    for c in chunks:
        covered.update(c.split())
    assert covered == set(words)
    if not words:
        assert chunks == []


@settings(max_examples=30, deadline=None)
@given(st.lists(
    st.tuples(st.sampled_from(["patient", "doctor"]),
              st.lists(st.sampled_from("ache pain day week bad mild".split()),
                       min_size=1, max_size=10)),
    min_size=1, max_size=15,
))
def test_chunk_dialogue_never_splits_a_turn(turns):
    lines = [f"{spk}: {' '.join(words)}" for spk, words in turns]
    chunks = chunk_dialogue(lines, max_words=25, overlap=0)
    combined = "\n".join(chunks)
    # Whole utterances pack into chunks; a turn shorter than the window is
    # never split across chunks.
    for line in lines:
        assert line in combined


@settings(max_examples=30, deadline=None)
@given(st.text(max_size=300))
def test_extractor_never_raises(text):
    out = extractor_generate(text)
    assert "extracted" in out
    assert "retrieval_query" in out
