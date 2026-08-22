from rag_runtime.chunking import (
    DEFAULT_MAX_WORDS,
    chunk_dialogue,
    chunk_words,
    docs_from_json,
    extract_meta,
)


def test_short_text_single_chunk():
    assert chunk_words("one two three") == ["one two three"]


def test_long_text_windows_respect_max_words():
    words = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_words(words, max_words=180, overlap=40)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 180 for c in chunks)
    # overlap: consecutive chunks share words
    assert set(chunks[0].split()) & set(chunks[1].split())


def test_dialogue_never_splits_mid_turn():
    turns = [f"speaker: utterance {i} " + "word " * 30 for i in range(12)]
    chunks = chunk_dialogue(turns, max_words=100, overlap=20)
    joined = "\n".join(chunks)
    for turn in turns:
        assert turn.strip() in joined
    # every chunk boundary falls on a turn boundary
    for c in chunks:
        assert all(line.startswith("speaker:") for line in c.split("\n"))


def test_extract_meta_types():
    ehr = extract_meta({"chexpert_label": "Pneumonia", "age": 60, "sex": "F"}, "ehr.json", "item_0")
    assert ehr["source_type"] == "ehr"
    assert ehr["condition_label"] == "Pneumonia"
    conv = extract_meta({"utterances": ["patient: hi"]}, "conv.json", "item_1")
    assert conv["source_type"] == "conversation"


def test_docs_from_json_chunk_sections(tmp_path):
    long_item = {"utterances": [f"patient: line {i} " + "pad " * 40 for i in range(20)]}
    path = tmp_path / "corpus.json"
    import json
    path.write_text(json.dumps([long_item]))
    docs = docs_from_json(path, max_words=100, overlap=20)
    assert len(docs) > 1
    sections = [m["section"] for _, m in docs]
    assert sections[0] == "item_0.c0"
    assert len(set(sections)) == len(sections), "chunk sections must be unique for citations"
    assert all(len(t.split()) <= DEFAULT_MAX_WORDS for t, _ in docs)


def test_dialogue_short_tail_merged_not_dropped():
    turns = ["speaker: " + "word " * 90, "speaker: " + "word " * 85, "speaker: yes okay"]
    chunks = chunk_dialogue(turns, max_words=100, overlap=20)
    assert "yes okay" in "\n".join(chunks), "short tail must merge, not vanish"
