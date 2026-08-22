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


# --------------- cross-encoder re-ranking ---------------
_cross_encoder = None


def _reranker_cfg() -> Dict[str, Any]:
    cfg = _cfg.get("reranker", {}) or {}
    env = os.getenv("RAG_RERANK")
    if env is not None:
        cfg = {**cfg, "enabled": env.strip().lower() in ("1", "true", "yes", "on")}
    return cfg


def _get_cross_encoder(model_name: str):
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(model_name)
        print(f"[Retriever] Cross-encoder loaded: {model_name}")
    return _cross_encoder


def _candidate_k(top_k: int) -> int:
    retrieval_cfg = _cfg.get("retrieval", {}) or {}
    k = int(os.getenv("RAG_CANDIDATE_K", str(retrieval_cfg.get("candidate_k", 20))))
    return max(k, top_k)


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

        rerank_cfg = _reranker_cfg()
        use_rerank = bool(rerank_cfg.get("enabled", False))
        k = min(_candidate_k(self.top_k) if use_rerank else self.top_k, len(self.texts))
        scores, idxs = self.index.search(q_emb, k)

        docs = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            docs.append(_Doc(
                page_content=self.texts[idx],
                metadata={**self.metas[idx], "score": float(score)},
            ))

        if use_rerank and len(docs) > self.top_k:
            try:
                ce = _get_cross_encoder(
                    rerank_cfg.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
                pairs = [[query, d.page_content] for d in docs]
                ce_scores = ce.predict(pairs)
                ranked = sorted(zip(ce_scores, docs), key=lambda x: float(x[0]), reverse=True)
                docs = []
                for ce_score, doc in ranked[: self.top_k]:
                    doc.metadata["rerank_score"] = float(ce_score)
                    docs.append(doc)
                return docs
            except Exception as e:
                print(f"[Retriever] Re-ranking failed, using vector order: {e}")

        return docs[: self.top_k]


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


def warm_up() -> None:
    """Eagerly initialize the store and the cross-encoder so the first live
    query doesn't pay model-load (or download) latency."""
    _ensure_store_initialized()
    cfg = _reranker_cfg()
    if cfg.get("enabled", False):
        try:
            _get_cross_encoder(cfg.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
        except Exception as e:
            print(f"[Retriever] Cross-encoder warm-up failed: {e}")


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
