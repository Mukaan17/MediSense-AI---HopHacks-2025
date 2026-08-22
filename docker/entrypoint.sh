#!/bin/sh
set -e

# Build the FAISS knowledge base on first boot (rag_store is a volume, so
# subsequent starts reuse it). The retriever initializes once per process,
# so the build must finish before uvicorn starts.
if [ ! -f "${RAG_PERSIST_DIR:-./rag_store}/index.faiss" ]; then
    echo "[entrypoint] rag_store missing - building knowledge base"
    python3 -m rag_runtime.build_faiss_kb --reset || \
        echo "[entrypoint] KB build failed; serving with empty retrieval context"
fi

WORKERS="${UVICORN_WORKERS:-1}"
exec uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
