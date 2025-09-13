import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
from chromadb.utils import embedding_functions


def load_json_records(input_path: str) -> List[Any]:
    with open(input_path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # If it's a dict with a top-level key containing a list
    for key in ["records", "data", "items", "examples", "conversations"]:
        if key in data and isinstance(data[key], list):
            return data[key]
    # Fallback to wrapping the dict
    return [data]


def record_to_text_and_meta(rec: Any, idx: int) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"source": "english_train_json", "section": f"item_{idx}"}
    text = None

    if isinstance(rec, str):
        text = rec
    elif isinstance(rec, dict):
        # Preferred fields
        for key in ["dialogue", "conversation", "text"]:
            if key in rec and isinstance(rec[key], str):
                text = rec[key]
                break

        # Structured fields
        if text is None and "utterances" in rec and isinstance(rec["utterances"], list):
            text = "\n".join([str(u) for u in rec["utterances"]])

        if text is None and "messages" in rec and isinstance(rec["messages"], list):
            parts = []
            for m in rec["messages"]:
                if isinstance(m, dict):
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    parts.append(f"{role}: {content}")
                else:
                    parts.append(str(m))
            text = "\n".join(parts)

        # Metadata hints
        for mk in ["title", "topic", "section", "desc", "description"]:
            if mk in rec and isinstance(rec[mk], str):
                meta["section"] = rec[mk]
                break

        # Fallback: flatten string values
        if text is None:
            str_vals = []
            for k, v in rec.items():
                if isinstance(v, str):
                    str_vals.append(v)
                elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                    str_vals.extend(v)
            text = "\n".join(str_vals) if str_vals else json.dumps(rec, ensure_ascii=False)
    else:
        text = str(rec)

    return text, meta


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Build Chroma vector store from training JSON")
    parser.add_argument("--input", required=True, help="Path to English Train.json or similar")
    parser.add_argument("--persist_dir", required=True, help="Directory to persist Chroma index")
    parser.add_argument("--collection", required=True, help="Collection name")
    parser.add_argument("--emb_model", default="sentence-transformers/all-mpnet-base-v2", help="Sentence-Transformers model")
    args = parser.parse_args()

    input_path = Path(args.input)
    persist_dir = Path(args.persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    # Init Chroma
    client = chromadb.PersistentClient(path=str(persist_dir))
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=args.emb_model)
    collection = client.get_or_create_collection(name=args.collection, embedding_function=embedding_fn)

    records = load_json_records(str(input_path))
    ids: List[str] = []
    docs: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    doc_id = 0
    for i, rec in enumerate(records):
        text, meta = record_to_text_and_meta(rec, i)
        if not text:
            continue
        for j, chunk in enumerate(chunk_text(text)):
            ids.append(f"doc_{doc_id}")
            docs.append(chunk)
            chunk_meta = dict(meta)
            chunk_meta["chunk"] = j
            metadatas.append(chunk_meta)
            doc_id += 1

        # Flush in batches to avoid huge memory
        if len(ids) >= 512:
            collection.add(ids=ids, documents=docs, metadatas=metadatas)
            ids, docs, metadatas = [], [], []

    if ids:
        collection.add(ids=ids, documents=docs, metadatas=metadatas)

    print(f"Indexed {doc_id} chunks into collection '{args.collection}' at {persist_dir}")


if __name__ == "__main__":
    main()


