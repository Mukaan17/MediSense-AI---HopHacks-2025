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

## Mutation testing (report-only, decision D6)

`mutmut` against focused test runners, recorded 2026-08-22:

- `core/utils.py` (LLM JSON parsing + helpers): **73% killed** (24/33).
  The 9 survivors are log-string mutations and one behavior-equivalent
  guard rewrite - acceptable residue.
- `rag_runtime/chunking.py`: **48% killed** (74/154). Survivors
  concentrate in `extract_meta`/`docs_from_json` (metadata extraction),
  which the chunking tests don't target - the next place to add tests.

CI runs the report weekly (`mutation-tests` job, workflow_dispatch or
schedule); it can never block a merge.

## Retrieval quality

`tests/test_retrieval_eval.py` guards the KB with a labeled query set:
topical recall@5 must stay >= 0.8 over the 811-chunk store (currently
5/5). Rebuilding the KB or swapping the embedding model must keep this
green.

## Model benchmarks (I10 groundwork, recorded 2026-08-22)

- **STT** (`scripts/stt_benchmark.py`, committed speech fixture, CPU int8):
  tiny.en p50 0.78 s / WER 0.05; base.en p50 1.17 s / WER 0.05. Same
  accuracy on this fixture at ~50% more latency - tiny.en keeps the live
  slot on evidence, not habit. Re-run against a larger recorded set before
  any change (`models/registry.yaml`).
- **Embeddings** (`scripts/embedding_experiment.py`): all-MiniLM-L6-v2 vs
  NeuML/pubmedbert-base-embeddings both score 1.00 topical recall@5 on
  the 5-query labeled set - the set is too small to discriminate. Grow
  the labeled set before an adoption decision; no swap made.
- **Calibration**: temperature scaling is wired into the imaging head
  (`CXR_CALIBRATION`, identity when unfitted); fitting requires a real
  held-out eval set (owner: dataset access), gate via
  `scripts/model_gate.py`.

## Supply-chain status (last local audit)

Both CI audits are **blocking** as of I17, and the image-build jobs gate
on them plus a Trivy scan of the built image (fixable HIGH/CRITICAL
fails the build), generate an SPDX SBOM artifact (syft), and cosign-sign
the pushed digest when `COSIGN_PRIVATE_KEY` is configured. Accepted
findings are ignored by exact ID (`pip-audit --ignore-vuln`,
`.trivyignore`); every ignore must have a triage entry here.

### Accepted findings (triage)

- **ecdsa 0.19.2 - PYSEC-2026-1325 / CVE-2024-23342** (Minerva timing
  attack on P-256). Transitive of python-jose; no fixed release exists.
  Retires when python-jose drops ecdsa or a fixed ecdsa ships.
- **transformers 4.57.x - PYSEC-2025-217, PYSEC-2026-2288/2289/2290**
  (CVE-2025-14929, CVE-2026-1839, CVE-2026-4372, CVE-2026-5241). Fixes
  land in transformers 5.x, which requires sentence-transformers
  2.7.0 -> 6.0.0 - an embedding-stack major that forces a KB rebuild and
  retrieval re-eval, so it is a scheduled work package, not a rider. All
  four are load-untrusted-model vectors; this deployment loads only the
  pinned MiniLM/ms-marco models. Outside the CI-audited light set
  (caught by the Trivy image scan; listed in `.trivyignore`).

### Fixed by upgrade

- `python-jose >= 3.5.0` (I-series start): PYSEC-2024-232/233,
  PYSEC-2025-185.
- `fastapi 0.116.1 -> 0.141.1` + `starlette 0.47.3 -> 1.6.0` (I17):
  cleared six starlette advisories, including PYSEC-2026-161 (Host-header
  poisoning of `request.url.path`, which this app's path-based auth
  exemptions made directly relevant) and PYSEC-2026-1942 (Range-header
  DoS). The exported `openapi.json` was byte-identical across the
  upgrade; all 147 backend tests pass unchanged.
- npm: `npm audit fix` (54 -> 28, criticals cleared), then the
  CRA -> Vite migration (I3b) cleared the react-scripts transitives and
  a postcss bump closed the last advisory: **0 npm audit findings**.
  `npm audit --audit-level=high` is safely blocking at zero.
- CI's audit job upgrades pip/setuptools before auditing so findings
  against the runner image's bundled tooling (pip 24.x, setuptools 79.x)
  don't masquerade as app findings.

Dependabot (`.github/dependabot.yml`) opens weekly grouped update PRs
for pip, npm, and GitHub Actions; the blocking `supply-chain` job
re-runs both audits on every push.
