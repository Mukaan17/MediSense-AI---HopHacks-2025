# Performance & Quality Baselines

Recorded 2026-08-22 on a CPU-only container (single `uvicorn` worker,
demo mode, no LLM keys - the coach step degrades, everything else runs).
Re-measure with `scripts/ws_load_test.py` after pipeline changes and
update this file; a regression against these numbers is a finding.

## Live-case WebSocket pipeline (`/ws/case/{id}`)

Per-utterance HUD latency (extraction -> retrieval + rerank -> fusion ->
evidence -> HUD), measured client-side:

| Concurrent cases | Utterances/case | p50 | p90 | p95 | max |
|---|---|---|---|---|---|
| 5  | 5 | 1,640 ms | 2,002 ms | 2,156 ms | 2,196 ms |
| 10 | 5 | 2,748 ms | 4,093 ms | 4,384 ms | 5,133 ms |

Reading: the p95 < 3 s CPU-only budget holds at 5 concurrent live cases
per worker and is exceeded at 10. Scale-out guidance: size at ~5 live
cases per CPU worker (`UVICORN_WORKERS`, then ECS task count), and alert
on the `request_latency` p95 metric rather than assuming this table.

Repro:

    .venv/bin/python -m uvicorn api.server:app --port 8000 &
    .venv/bin/python scripts/ws_load_test.py --cases 5 --utterances 5

## Test coverage (full local dependency set)

`pytest --cov=api --cov=core --cov=rag_runtime`: **56% lines** across 71
tests. Best-covered: chunking, extraction, evidence, retriever, auth,
routes. Known blind spots (deliberate - degraded-mode environment):
`voice_transcription` (18%), `modeling_biomedclip` (7%), LLM invoke paths
in `llm_client` (36%), `diagnosis/differential` + `risk` (LLM-path heavy).
CI prints coverage on every run; treat drops in the well-covered modules
as review findings.

Frontend (jest): unit coverage concentrated in `lib/` (reportMapper,
wsClient normalization); components are covered by the Playwright smoke
(`frontend/e2e/`), not jest.

## Retrieval quality

`tests/test_retrieval_eval.py` guards the KB with a labeled query set:
topical recall@5 must stay >= 0.8 over the 811-chunk store (currently
5/5). Rebuilding the KB or swapping the embedding model must keep this
green.

## Supply-chain status (last local audit)

- `pip-audit`: python-jose upgraded to >= 3.5.0 (fixed PYSEC-2024-232/233,
  PYSEC-2025-185). Remaining known findings: `ecdsa` (transitive of
  python-jose, no fixed release), `transformers 4.57.x` (pinned by the
  sentence-transformers stack; scheduled-update lane item).
- `npm audit fix` applied: 54 -> 28 findings (2 critical -> 0); the
  CRA -> Vite migration (I3b) then cleared the react-scripts transitives
  and a postcss bump closed the last advisory: **0 npm audit findings**.
  Vite also cut the production build from ~40 s to ~2 s.
- Dependabot (`.github/dependabot.yml`) now opens weekly grouped update
  PRs for pip, npm, and GitHub Actions; CI's advisory `supply-chain` job
  re-runs both audits on every push.
