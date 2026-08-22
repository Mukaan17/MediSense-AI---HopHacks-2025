#!/usr/bin/env python3
"""Build FAISS KB for RAG (avoids ChromaDB SQLite lock issues on macOS).

Usage:
  python3 -m rag_runtime.build_faiss_kb --reset \
    --files "English Train.json" "ehr_with_images.json"
"""

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from .chunking import (
    DEFAULT_MAX_WORDS,
    DEFAULT_OVERLAP_WORDS,
    docs_from_json,
)


def _load_chunking_cfg() -> Dict[str, Any]:
    try:
        from core.config import load_rag
        return (load_rag() or {}).get("chunking", {}) or {}
    except Exception:
        return {}


def _default_files(repo_root: Path) -> List[Path]:
    candidates = [
        repo_root / "English Train.json",
        repo_root / "English Dev.json",
        repo_root / "English Test.json",
        repo_root / "Synthetic English Train Data.json",
        repo_root / "ehr_with_images.json",
    ]
    return [p for p in candidates if p.exists()]


def build_kb(files: List[Path], emb_model: str, persist_dir: Path, reset: bool,
             max_words: int = DEFAULT_MAX_WORDS,
             overlap: int = DEFAULT_OVERLAP_WORDS,
             chunking_enabled: bool = True) -> None:
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

    # Collect documents (chunked so each fits the embedding model's window)
    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    item_count = 0
    for fp in files:
        if fp.suffix.lower() == ".json":
            docs = docs_from_json(fp, max_words=max_words, overlap=overlap,
                                  chunking_enabled=chunking_enabled)
            item_count += sum(1 for _, m in docs if m.get("chunk_idx", 0) == 0)
            for text, meta in docs:
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

    if item_count:
        print(f"[KB] {item_count} corpus items -> {len(texts)} chunks")
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

    # Save index, texts, and metadata. JSON, not pickle: the store may sit on
    # a shared volume, and JSON removes the deserialization attack class.
    faiss.write_index(index, str(persist_dir / "index.faiss"))
    with open(persist_dir / "texts.json", "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False)
    with open(persist_dir / "metas.json", "w", encoding="utf-8") as f:
        json.dump(metas, f, ensure_ascii=False)
    from datetime import datetime, timezone
    with open(persist_dir / "config.json", "w") as f:
        json.dump({
            "emb_model": emb_model,
            "dim": dim,
            "count": len(texts),
            "files": [p.name for p in files],
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, f, indent=2)
    # Drop stale pickle files from pre-JSON builds so nothing loads them.
    for legacy in ("texts.pkl", "metas.pkl"):
        try:
            (persist_dir / legacy).unlink(missing_ok=True)
        except OSError as e:
            print(f"[WARN] Could not remove legacy {legacy}: {e}")

    print(f"[KB] Done. Indexed {len(texts)} documents (dim={dim}) → {persist_dir}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build FAISS KB for RAG")
    parser.add_argument("--embeddings", default=os.getenv("RAG_EMB_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    parser.add_argument("--persist_dir", default=os.getenv("RAG_PERSIST_DIR", str(repo_root / "rag_store")))
    parser.add_argument("--files", nargs="*", default=[str(p) for p in _default_files(repo_root)])
    parser.add_argument("--reset", action="store_true")
    chunk_cfg = _load_chunking_cfg()
    parser.add_argument("--max_words", type=int,
                        default=int(chunk_cfg.get("max_words", DEFAULT_MAX_WORDS)))
    parser.add_argument("--overlap_words", type=int,
                        default=int(chunk_cfg.get("overlap_words", DEFAULT_OVERLAP_WORDS)))
    parser.add_argument("--no_chunking", action="store_true",
                        default=not bool(chunk_cfg.get("enabled", True)))
    args = parser.parse_args()

    build_kb(
        files=[Path(x) for x in args.files],
        emb_model=args.embeddings,
        persist_dir=Path(args.persist_dir),
        reset=args.reset,
        max_words=args.max_words,
        overlap=args.overlap_words,
        chunking_enabled=not args.no_chunking,
    )


if __name__ == "__main__":
    main()
