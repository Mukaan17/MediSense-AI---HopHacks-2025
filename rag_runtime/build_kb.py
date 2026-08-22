#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build Chroma KB for RAG with a single canonical implementation.

Usage:
  python -m rag_runtime.build_kb --reset \
    --embeddings sentence-transformers/all-MiniLM-L6-v2 \
    --persist_dir ./rag_store \
    --collection conversations \
    --files "English Train.json" "ehr_with_images.json"
"""

import argparse
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from .chunking import docs_from_json


def _default_files(repo_root: Path) -> List[Path]:
    candidates = [
        repo_root / "English Train.json",
        repo_root / "English Dev.json",
        repo_root / "English Test.json",
        repo_root / "ehr_with_images.json",
    ]
    return [p for p in candidates if p.exists()]


def build_kb(files: List[Path], emb_model: str, persist_dir: Path, collection: str, reset: bool) -> None:
    if reset and persist_dir.exists():
        print(f"[KB] Resetting store at {persist_dir}")
        shutil.rmtree(persist_dir)

    persist_dir.mkdir(parents=True, exist_ok=True)

    print(f"[KB] Embedding model: {emb_model}")
    print(f"[KB] Persist dir    : {persist_dir}")
    print(f"[KB] Collection     : {collection}")
    print(f"[KB] Files          : {[p.name for p in files]}")

    embeddings = HuggingFaceEmbeddings(model_name=emb_model)
    vs = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    for fp in files:
        if fp.suffix.lower() == ".json":
            for text, meta in docs_from_json(fp):
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

    print(f"[KB] Adding {len(texts)} documents …")
    vs.add_texts(texts=texts, metadatas=metas)
    vs.persist()
    try:
        count = vs._collection.count()
    except Exception:
        count = -1
    print(f"[KB] Done. Indexed documents: {count if count >= 0 else 'unknown'}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build Chroma KB for RAG")
    parser.add_argument(
        "--embeddings",
        default=os.getenv("RAG_EMB_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        help="HuggingFace embeddings model name",
    )
    parser.add_argument(
        "--persist_dir",
        default=os.getenv("RAG_PERSIST_DIR", str(repo_root / "rag_store")),
        help="Directory to persist Chroma store",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("RAG_COLLECTION", "conversations"),
        help="Chroma collection name",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[str(p) for p in _default_files(repo_root)],
        help="List of files to ingest (JSON or TXT)",
    )
    parser.add_argument("--reset", action="store_true", help="Wipe store before building")
    args = parser.parse_args()

    build_kb(
        files=[Path(x) for x in args.files],
        emb_model=args.embeddings,
        persist_dir=Path(args.persist_dir),
        collection=args.collection,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
