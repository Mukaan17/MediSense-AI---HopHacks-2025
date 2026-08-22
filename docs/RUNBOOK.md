# Operations Runbook

On-call procedures for the MediSense backend + frontend. Alert rules that
point here live in `deploy/prometheus-alerts.yml`; latency budgets in
`docs/PERF_BASELINE.md`.

## Service map

- **Backend**: FastAPI, `uvicorn api.server:app` (entrypoint
  `docker/entrypoint.sh`, `UVICORN_WORKERS` processes). State: in-memory or
  Redis case store (`REDIS_URL`), FAISS store on disk (`RAG_PERSIST_DIR`).
- **Worker**: `arq worker.settings.WorkerSettings` (same image) consumes
  finalize-report jobs when `FINALIZE_MODE=queue`; results flow back
  through the shared case store and clients poll
  `GET /api/case/{id}/report`. Without the worker or Redis, finalize runs
  inline exactly as before. Live STT concurrency is `STT_WORKERS`
  (default 1).
- **Frontend**: nginx serving the Vite build (runtime config injected
  into `config.js` by the container entrypoint), proxying unknown paths
  and `/ws/` to the backend (`frontend/nginx.conf`).
- **Modes**: `APP_MODE=demo` (open, synthetic EHR) vs `APP_MODE=clinical`
  (auth required - httpOnly session cookie or Bearer JWT, synthetic EHR
  refused; boot fails without `AUTH_SECRET_KEY` + `AUTH_USERS_FILE`).

## Restart / reload

- **Full restart (compose)**: `docker compose restart backend` - state in
  Redis survives; in-memory case store does not (live cases are lost, tell
  users to re-record).
- **Reload EHR without restart**: `POST /reload_ehr` (auth in clinical).
- **Reload the RAG store after a KB rebuild**: `POST /reload_retriever` -
  re-warms on a background thread; check `/health` `doc_count` afterwards.
- **Frontend only**: `docker compose restart frontend` (stateless).

## KB rebuild

    .venv/bin/python -m rag_runtime.build_faiss_kb                        # local
    docker compose exec backend python -m rag_runtime.build_faiss_kb      # in-container
    # never pass --reset against a bind-mounted store (rmtree on a mount fails)

Then `POST /reload_retriever`. Verify: `/health` doc_count matches the
build log, and `pytest tests/test_retrieval_eval.py` stays green
(topical recall@5 >= 0.8). The store is JSON (`texts.json`/`metas.json`);
`.pkl` from pre-migration builds is read-compatible but should be rebuilt.

## Model refresh

- **LLM routing** is config: `config/models.yaml` (+ `LIVE_MODEL` /
  `FINAL_MODEL` env overrides). No restart needed for env-read paths;
  restart workers to be safe after editing the YAML.
- **Embedding model**: changing `RAG_EMB_MODEL` requires a KB rebuild
  (dimensions must match the FAISS index) - rebuild, then reload.
- **Imaging checkpoint**: replace the file at `CXR_CKPT`, restart. Check
  `/health` `image_model_loaded: true`.
- **STT**: faster-whisper model name is in `core/live_stt.py`; changing it
  requires a deploy.

## Observability stack

    docker compose -f docker-compose.yml -f docker-compose.observability.yml up

Prometheus (:9090) scrapes the backend and evaluates
`deploy/prometheus-alerts.yml`; Grafana (:3001, admin password via
`GRAFANA_ADMIN_PASSWORD`) auto-provisions the "MediSense Backend"
dashboard; Alertmanager (:9093) routes alerts - **configure a real
receiver** in `deploy/observability/alertmanager.yml` before relying on
it. Clinical mode: give Prometheus a service bearer token for /metrics
(commented block in `deploy/observability/prometheus.yml`).

## Triage by alert

### backend-down
1. `docker compose ps` / ECS task status; container logs first 50 lines -
   clinical boot refuses to start on missing `AUTH_SECRET_KEY` (exit at
   `validate_clinical_config`).
2. Disk full on the KB/EFS volume also fails boot - check `df`.

### high-error-rate
1. `/health` first: degraded subsystems show there (doc_count null,
   image_model_loaded false).
2. `logs/audit.log` (JSONL) - filter `"status": 5` to find the failing
   path; `X-Request-ID` correlates with app logs.
3. Common causes: LLM keys revoked (503s on report endpoints - fallback
   covers live paths), Redis unreachable (case endpoints), KB volume
   unmounted (empty retrieval, not 5xx).

### auth-failures
1. Spike of 401s with varied usernames in `logs/audit.log`
   (`event: login_failed`) = probing; block at the ALB/nginx layer.
2. Uniform 401s from one client = expired token loop in a stale frontend
   session; harmless, but confirm the frontend re-login modal appears.

### slow-pipeline
1. `medisense_stage_latency_*` on `/metrics` shows which stage (extract /
   retrieve / fuse) regressed.
2. Retrieve slow: cross-encoder running on an undersized CPU - lower
   `RAG_CANDIDATE_K` or disable `RAG_RERANK` as a stopgap.
3. Overall slow under load: more live cases than ~5 per worker
   (docs/PERF_BASELINE.md) - scale `UVICORN_WORKERS` / task count.

### llm-failures
1. `medisense_llm_errors_total` by provider: anthropic failing means live
   coach fell back to Gemini (feature keeps working, latency rises);
   both failing means questions/report generation degrade to heuristics.
2. Check key validity and provider status pages; keys rotate via env, then
   restart workers.

### token-spend
1. `medisense_llm_tokens_total` by model: the final-report model is the
   expensive one; a spike usually means finalize is being called in a loop.
2. Audit log shows the calling user/path; rate-limit or revoke as needed.

## Backups / data

- `rag_store/` is rebuildable from the corpus JSONs - back up the corpus,
  not the index.
- `config/users.json` (clinical) and `logs/audit.log` are the two files
  that must be on durable storage; they are deliberately gitignored.
- Redis persistence is not configured in compose; treat live cases as
  ephemeral by design.
