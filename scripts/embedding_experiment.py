#!/usr/bin/env python3
"""Comparative embedding experiment: build a side-by-side KB with a
candidate embedding model and score both stores on the labeled retrieval
set. Adoption is a separate, reviewed decision - this script only reports.

Usage:
  python scripts/embedding_experiment.py NeuML/pubmedbert-base-embeddings
"""

import argparse
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

LABELED_QUERIES = [
    ("persistent cough with high fever for several days", ["cough", "fever"]),
    ("shortness of breath and chest tightness on exertion", ["breath", "chest"]),
    ("sore throat, runny nose and sneezing", ["throat", "nose", "cold"]),
    ("loss of taste and smell after exposure", ["taste", "smell", "covid"]),
    ("wheezing at night with a history of asthma", ["wheez", "asthma"]),
]
TOP_K = 5


def score_store(persist_dir: str, emb_model: str) -> float:
    import faiss
    import json
    import numpy as np
    from sentence_transformers import SentenceTransformer

    index = faiss.read_index(str(Path(persist_dir) / "index.faiss"))
    texts = json.loads((Path(persist_dir) / "texts.json").read_text())
    model = SentenceTransformer(emb_model)

    hits = 0
    for query, keywords in LABELED_QUERIES:
        q = np.array(model.encode([query]), dtype="float32")
        faiss.normalize_L2(q)
        _, idxs = index.search(q, TOP_K)
        blob = " ".join(texts[i].lower() for i in idxs[0] if i >= 0)
        if any(kw in blob for kw in keywords):
            hits += 1
    return hits / len(LABELED_QUERIES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Embedding A/B on the labeled retrieval set")
    parser.add_argument("candidate", help="HF sentence-embedding model id")
    parser.add_argument("--baseline-store", default=str(REPO_ROOT / "rag_store"))
    parser.add_argument("--baseline-model",
                        default="sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()

    from rag_runtime.build_faiss_kb import build_kb, _default_files

    with tempfile.TemporaryDirectory(prefix="rag_candidate_") as tmp:
        print(f"[exp] building candidate store with {args.candidate} ...")
        build_kb(files=_default_files(REPO_ROOT), emb_model=args.candidate,
                 persist_dir=Path(tmp), reset=False)

        baseline = score_store(args.baseline_store, args.baseline_model)
        candidate = score_store(tmp, args.candidate)

    print(f"\n[exp] topical recall@{TOP_K} on {len(LABELED_QUERIES)} labeled queries")
    print(f"  baseline  {args.baseline_model}: {baseline:.2f}")
    print(f"  candidate {args.candidate}: {candidate:.2f}")
    print("[exp] adopt only if the candidate is >= baseline here AND on a "
          "larger labeled set; record the decision in models/registry.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
