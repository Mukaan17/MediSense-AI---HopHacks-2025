# MediSense AI developer entry points.

.PHONY: help venv install kb serve frontend smoke test test-frontend build-frontend

help:
	@echo "make install         install backend dependencies into .venv"
	@echo "make kb              build the FAISS knowledge base into ./rag_store"
	@echo "make serve           run the API on :8000"
	@echo "make frontend        run the React dev server on :3000"
	@echo "make smoke           run endpoint + websocket smoke checks"
	@echo "make test            run the backend test suite"
	@echo "make test-frontend   type-check and unit-test the frontend"
	@echo "make build-frontend  production build of the frontend"

venv:
	python3 -m venv .venv

install: venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# The retriever initializes once per process: restart the API (or POST
# /reload_retriever) after rebuilding the knowledge base.
kb:
	python3 -m rag_runtime.build_faiss_kb --reset

serve:
	uvicorn api.server:app --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm start

smoke:
	python3 smoke_test.py --base-url http://localhost:8000

test:
	python3 -m pytest tests/ -q

test-frontend:
	cd frontend && npx tsc --noEmit && npm test -- --watchAll=false

build-frontend:
	cd frontend && npm run build
