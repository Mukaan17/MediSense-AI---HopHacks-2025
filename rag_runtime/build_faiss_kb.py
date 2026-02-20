#!/usr/bin/env python3
"""Build FAISS KB for RAG (avoids ChromaDB SQLite lock issues on macOS).

Usage:
  python3 -m rag_runtime.build_faiss_kb --reset \
    --files "English Train.json" "ehr_with_images.json"
"""

import argparse
import json
import os
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _default_files(repo_root: Path) -> List[Path]:
    candidates = [
        repo_root / "English Train.json",
        repo_root / "English Dev.json",
        repo_root / "English Test.json",
        repo_root / "Synthetic English Train Data.json",
        repo_root / "ehr_with_images.json",
    ]
    return [p for p in candidates if p.exists()]


def _flatten(obj: Any, sep: str = "\n") -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return sep.join([_flatten(x, sep) for x in obj if _flatten(x, sep)])
    if isinstance(obj, dict):
        return sep.join([f"{k}: {_flatten(v, sep)}" for k, v in obj.items() if _flatten(v, sep)])
    return str(obj)


def _read_json_docs(path: Path) -> List[Tuple[str, Dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to read {path.name}: {e}")
        return []

    docs = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            text = _flatten(item)
            if text.strip():
                docs.append((text, {"source": path.name, "section": f"item_{i}"}))
    elif isinstance(data, dict):
        for k, v in data.items():
            text = _flatten(v)
            if text.strip():
                docs.append((text, {"source": path.name, "section": str(k)}))
    return docs


def build_kb(files: List[Path], emb_model: str, persist_dir: Path, reset: bool) -> None:
    # Lazy imports to avoid issues at module level
    import numpy as np
    try:
        import faiss
    except ImportError:
        raise RuntimeError("Please install faiss-cpu: pip install faiss-cpu")
    from sentence_transformers import SentenceTransformer

    if reset and persist_dir.exists():
        print(f"[KB] Resetting store at {persist_dir}")
        shutil.rmtree(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    print(f"[KB] Embedding model: {emb_model}")
    print(f"[KB] Persist dir    : {persist_dir}")
    print(f"[KB] Files          : {[p.name for p in files]}")

    # Collect documents
    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    for fp in files:
        if fp.suffix.lower() == ".json":
            for text, meta in _read_json_docs(fp):
                texts.append(text)
                metas.append(meta)
        else:
            try:
                content = fp.read_text(encoding="utf-8")
                if content.strip():
                    texts.append(content)
                    metas.append({"source": fp.name})
            except Exception as e:
                print(f"[WARN] Failed to read {fp}: {e}")

    if not texts:
        print("[KB] Nothing to index. Aborting.")
        return

    print(f"[KB] Encoding {len(texts)} documents …")
    model = SentenceTransformer(emb_model)
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    embeddings = np.array(embeddings, dtype="float32")

    # Normalize for cosine similarity
    faiss.normalize_L2(embeddings)

    # Build FAISS index (Inner Product on normalized vectors = cosine similarity)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Save index, texts, and metadata
    faiss.write_index(index, str(persist_dir / "index.faiss"))
    with open(persist_dir / "texts.pkl", "wb") as f:
        pickle.dump(texts, f)
    with open(persist_dir / "metas.pkl", "wb") as f:
        pickle.dump(metas, f)
    with open(persist_dir / "config.json", "w") as f:
        json.dump({"emb_model": emb_model, "dim": dim, "count": len(texts)}, f, indent=2)

    print(f"[KB] Done. Indexed {len(texts)} documents (dim={dim}) → {persist_dir}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build FAISS KB for RAG")
    parser.add_argument("--embeddings", default=os.getenv("RAG_EMB_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    parser.add_argument("--persist_dir", default=os.getenv("RAG_PERSIST_DIR", str(repo_root / "rag_store")))
    parser.add_argument("--files", nargs="*", default=[str(p) for p in _default_files(repo_root)])
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    build_kb(
        files=[Path(x) for x in args.files],
        emb_model=args.embeddings,
        persist_dir=Path(args.persist_dir),
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
