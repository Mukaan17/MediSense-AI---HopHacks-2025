import os
from typing import Any
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from .config import load_rag

_cfg = load_rag()

PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", "./rag_store")
COLLECTION  = os.getenv("RAG_COLLECTION", "conversations")
EMB_MODEL   = os.getenv("RAG_EMB_MODEL", "sentence-transformers/all-mpnet-base-v2")

_emb = HuggingFaceEmbeddings(model_name=EMB_MODEL)
_vs  = Chroma(collection_name=COLLECTION, embedding_function=_emb, persist_directory=PERSIST_DIR)

def get_retriever():
    top_k = int(os.getenv("RAG_TOP_K", str(_cfg.get("top_k", 5))))
    if _cfg.get("mmr", {}).get("enabled", True):
        fetch_k = _cfg.get("mmr", {}).get("fetch_k", max(20, 3*top_k))
        lambda_mult = _cfg.get("mmr", {}).get("lambda_mult", 0.6)
        return _vs.as_retriever(search_type="mmr", search_kwargs={"k": top_k, "fetch_k": fetch_k, "lambda_mult": lambda_mult})
    return _vs.as_retriever(search_kwargs={"k": top_k})

def render_docs(docs: Any) -> str:
    lines = []
    for d in docs:
        src = d.metadata.get("source") or "english_train_json"
        sec = d.metadata.get("section", "")
        lines.append(f"Source={src} §{sec}\n{d.page_content}")
    return "\n\n".join(lines)

def get_doc_count() -> int:
    try:
        return _vs._collection.count()
    except Exception:
        return -1

def get_top_k() -> int:
    try:
        return int(os.getenv("RAG_TOP_K", str(_cfg.get("top_k", 5))))
    except Exception:
        return _cfg.get("top_k", 5)


