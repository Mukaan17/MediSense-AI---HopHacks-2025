import json
import os
import pickle
from pathlib import Path
from typing import Any, Dict, List

from .config import load_rag

_cfg = load_rag()

PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", "./rag_store")
COLLECTION  = os.getenv("RAG_COLLECTION", "conversations")
EMB_MODEL   = os.getenv("RAG_EMB_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


# --------------- lightweight doc wrapper ---------------
class _Doc:
    """Minimal document wrapper compatible with LangChain-style access."""
    def __init__(self, page_content: str, metadata: Dict[str, Any] = None):
        self.page_content = page_content
        self.metadata = metadata or {}


# --------------- fallback ---------------
class _FallbackRetriever:
    def get_relevant_documents(self, _query: str) -> List[_Doc]:
        return []


# --------------- FAISS retriever ---------------
class _FaissRetriever:
    def __init__(self, index, texts, metas, model, top_k: int):
        self.index = index
        self.texts = texts
        self.metas = metas
        self.model = model
        self.top_k = top_k

    def get_relevant_documents(self, query: str) -> List[_Doc]:
        import numpy as np
        import faiss

        q_emb = self.model.encode([query])
        q_emb = np.array(q_emb, dtype="float32")
        faiss.normalize_L2(q_emb)

        k = min(self.top_k, len(self.texts))
        scores, idxs = self.index.search(q_emb, k)

        docs = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            docs.append(_Doc(
                page_content=self.texts[idx],
                metadata={**self.metas[idx], "score": float(score)},
            ))
        return docs


# --------------- init logic ---------------
_retriever = None
_init_attempted = False


def _ensure_store_initialized() -> bool:
    global _retriever, _init_attempted
    if _retriever is not None:
        return True
    if _init_attempted:
        return False
    _init_attempted = True

    store_path = Path(PERSIST_DIR)

    # Try FAISS index first
    faiss_index_path = store_path / "index.faiss"
    if faiss_index_path.exists():
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            index = faiss.read_index(str(faiss_index_path))
            with open(store_path / "texts.pkl", "rb") as f:
                texts = pickle.load(f)
            with open(store_path / "metas.pkl", "rb") as f:
                metas = pickle.load(f)

            config_path = store_path / "config.json"
            emb_model = EMB_MODEL
            if config_path.exists():
                with open(config_path) as f:
                    emb_model = json.load(f).get("emb_model", EMB_MODEL)

            model = SentenceTransformer(emb_model)
            top_k = int(os.getenv("RAG_TOP_K", str(_cfg.get("top_k", 5))))
            _retriever = _FaissRetriever(index, texts, metas, model, top_k)
            print(f"[Retriever] FAISS index loaded: {len(texts)} docs, dim={index.d}")
            return True
        except Exception as e:
            print(f"[Retriever] FAISS init failed: {e}")

    # Fallback to ChromaDB
    try:
        from langchain_community.vectorstores import Chroma
        from langchain_community.embeddings import HuggingFaceEmbeddings

        collection = os.getenv("RAG_COLLECTION", "conversations")
        emb = HuggingFaceEmbeddings(model_name=EMB_MODEL)
        vs = Chroma(collection_name=collection, embedding_function=emb, persist_directory=PERSIST_DIR)
        top_k = int(os.getenv("RAG_TOP_K", str(_cfg.get("top_k", 5))))

        class _ChromaRetriever:
            def __init__(self, vs, top_k):
                self._vs = vs
                self._top_k = top_k
            def get_relevant_documents(self, query: str):
                return self._vs.as_retriever(search_kwargs={"k": self._top_k}).get_relevant_documents(query)

        _retriever = _ChromaRetriever(vs, top_k)
        print(f"[Retriever] ChromaDB loaded")
        return True
    except Exception as e:
        print(f"[Retriever] ChromaDB init failed: {e}")

    return False


def get_retriever():
    if not _ensure_store_initialized():
        return _FallbackRetriever()
    return _retriever


def render_docs(docs: Any) -> str:
    lines = []
    for d in docs:
        src = d.metadata.get("source") or "unknown"
        sec = d.metadata.get("section", "")
        score = d.metadata.get("score", "")
        score_str = f" (score={score:.3f})" if isinstance(score, float) else ""
        lines.append(f"Source={src} §{sec}{score_str}\n{d.page_content}")
    return "\n\n".join(lines)


def get_doc_count() -> int:
    if not _ensure_store_initialized():
        return 0
    if isinstance(_retriever, _FaissRetriever):
        return len(_retriever.texts)
    try:
        return _retriever._vs._collection.count()
    except Exception:
        return -1


def get_top_k() -> int:
    try:
        return int(os.getenv("RAG_TOP_K", str(_cfg.get("top_k", 5))))
    except Exception:
        return _cfg.get("top_k", 5)
