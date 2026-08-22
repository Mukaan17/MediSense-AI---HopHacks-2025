"""Retrieval-quality eval against the built RAG store.

A small labeled query set guards the KB: if an embedding, chunking, or
index regression ships, topical recall@k drops and this fails. Skipped
when the store or the embedding stack is absent (e.g. the light CI set).
"""

from pathlib import Path

import pytest

STORE = Path(__file__).resolve().parents[1] / "rag_store"

pytestmark = pytest.mark.skipif(
    not (STORE / "index.faiss").exists()
    or not ((STORE / "texts.json").exists() or (STORE / "texts.pkl").exists()),
    reason="rag_store not built",
)

# Each query names topical keywords; retrieval is a hit when any top-k text
# mentions any of them. Deliberately coarse - this is a regression tripwire,
# not a benchmark.
LABELED_QUERIES = [
    ("persistent cough with high fever for several days", ["cough", "fever"]),
    ("shortness of breath and chest tightness on exertion", ["breath", "chest"]),
    ("sore throat, runny nose and sneezing", ["throat", "nose", "cold"]),
    ("loss of taste and smell after exposure", ["taste", "smell", "covid"]),
    ("wheezing at night with a history of asthma", ["wheez", "asthma"]),
]

TOP_K = 5


@pytest.fixture(scope="module")
def retriever():
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("faiss")
    from core import retriever as core_retriever
    # Other tests hit /reload_retriever, which re-warms on a background
    # thread; reset and init synchronously so this module never races it.
    core_retriever.reset()
    r = core_retriever.get_retriever()
    if not core_retriever.get_doc_count():
        pytest.skip("retriever initialized empty")
    return r


def test_topical_recall_at_k(retriever):
    hits = 0
    misses = []
    for query, keywords in LABELED_QUERIES:
        docs = retriever.get_relevant_documents(query)[:TOP_K]
        assert docs, f"no documents retrieved for: {query}"
        text = " ".join(d.page_content.lower() for d in docs)
        if any(kw in text for kw in keywords):
            hits += 1
        else:
            misses.append(query)
    recall = hits / len(LABELED_QUERIES)
    assert recall >= 0.8, f"topical recall@{TOP_K} {recall:.2f}; missed: {misses}"


def test_results_carry_scores_and_metadata(retriever):
    docs = retriever.get_relevant_documents(LABELED_QUERIES[0][0])[:TOP_K]
    for d in docs:
        assert d.metadata.get("source"), "every chunk must attribute its source"
        assert isinstance(d.metadata.get("score"), float)
