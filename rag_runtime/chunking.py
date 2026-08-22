#!/usr/bin/env python3
"""Chunking and metadata extraction shared by the KB builders.

Documents are split into word windows sized for the embedding model:
all-MiniLM-L6-v2 truncates at 256 tokens, so the default window of 180 words
(~230 tokens) keeps every chunk fully inside the model's context. Dialogue
items are split on utterance boundaries instead of mid-turn.

Metadata (source_type / condition_label / age / sex) is stored for citation
display; retrieval itself remains pure vector search.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_MAX_WORDS = 180
DEFAULT_OVERLAP_WORDS = 40
MIN_CHUNK_WORDS = 10


def flatten(obj: Any, sep: str = "\n") -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        parts = [flatten(x, sep) for x in obj]
        return sep.join([p for p in parts if p])
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            t = flatten(v, sep)
            if t:
                lines.append(f"{k}: {t}")
        return sep.join(lines)
    return str(obj)


def chunk_words(text: str, max_words: int = DEFAULT_MAX_WORDS,
                overlap: int = DEFAULT_OVERLAP_WORDS) -> List[str]:
    """Split text into overlapping word windows."""
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text.strip()]

    step = max(1, max_words - overlap)
    chunks: List[str] = []
    start = 0
    while start < len(words):
        window = words[start:start + max_words]
        # A short tail is already covered by the previous window's overlap.
        if chunks and len(window) < MIN_CHUNK_WORDS:
            break
        chunks.append(" ".join(window))
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def chunk_dialogue(turns: List[str], max_words: int = DEFAULT_MAX_WORDS,
                   overlap: int = DEFAULT_OVERLAP_WORDS) -> List[str]:
    """Greedily pack whole utterances into chunks; never split mid-turn unless
    a single utterance alone exceeds the window."""
    chunks: List[str] = []
    current: List[str] = []
    count = 0
    for turn in turns:
        text = flatten(turn).strip()
        if not text:
            continue
        n = len(text.split())
        if n > max_words:
            if current:
                chunks.append("\n".join(current))
                current, count = [], 0
            chunks.extend(chunk_words(text, max_words, overlap))
            continue
        if count + n > max_words and current:
            chunks.append("\n".join(current))
            current, count = [], 0
        current.append(text)
        count += n
    if current:
        chunks.append("\n".join(current))
    # Dialogue packing has no overlap, so a short tail chunk would be lost
    # corpus text if dropped - merge it into the previous chunk instead.
    if len(chunks) > 1 and len(chunks[-1].split()) < MIN_CHUNK_WORDS:
        tail = chunks.pop()
        chunks[-1] = chunks[-1] + "\n" + tail
    return chunks


def extract_meta(item: Any, source_name: str, section: str) -> Dict[str, Any]:
    """Semantic metadata per corpus item. Stored for citation display and
    future filtering; retrieval does not currently rank by it."""
    meta: Dict[str, Any] = {"source": source_name, "section": section}
    if isinstance(item, dict):
        keys = item.keys()
        if "chexpert_label" in keys or "xray_path" in keys:
            meta["source_type"] = "ehr"
        elif "utterances" in keys or "conversation" in keys:
            meta["source_type"] = "conversation"
        else:
            meta["source_type"] = "knowledge"
        for field in ("Diagnosis", "label", "condition", "chexpert_label", "diagnosis"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                meta["condition_label"] = value.strip()
                break
        if item.get("age") is not None:
            meta["age"] = item["age"]
        sex = item.get("sex") or item.get("gender")
        if isinstance(sex, str) and sex.strip():
            meta["sex"] = sex.strip()
    else:
        meta["source_type"] = "knowledge"
    return meta


def _item_chunks(item: Any, max_words: int, overlap: int) -> List[str]:
    if isinstance(item, dict) and isinstance(item.get("utterances"), list):
        turns: List[str] = []
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            turns.append(description.strip())
        turns.extend(item["utterances"])
        return chunk_dialogue(turns, max_words, overlap)
    text = flatten(item)
    if not text.strip():
        return []
    return chunk_words(text, max_words, overlap)


def docs_from_json(path: Path, max_words: int = DEFAULT_MAX_WORDS,
                   overlap: int = DEFAULT_OVERLAP_WORDS,
                   chunking_enabled: bool = True) -> List[Tuple[str, Dict[str, Any]]]:
    """Read a JSON corpus file and yield (chunk_text, metadata) pairs.

    Chunk sections are labeled item_N.cJ so citations stay unambiguous after
    chunking (render_docs shows 'Source=<file> §<section>')."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to read {path.name}: {e}")
        return []

    if isinstance(data, list):
        items = [(f"item_{i}", item) for i, item in enumerate(data)]
    elif isinstance(data, dict):
        items = [(str(k), v) for k, v in data.items()]
    else:
        items = [("item_0", data)]

    docs: List[Tuple[str, Dict[str, Any]]] = []
    for section, item in items:
        meta = extract_meta(item, path.name, section)
        if chunking_enabled:
            chunks = _item_chunks(item, max_words, overlap)
        else:
            text = flatten(item)
            chunks = [text] if text.strip() else []
        total = len(chunks)
        for j, chunk in enumerate(chunks):
            m = dict(meta)
            if total > 1:
                m["section"] = f"{section}.c{j}"
            m["chunk_idx"] = j
            m["total_chunks"] = total
            docs.append((chunk, m))
    return docs
