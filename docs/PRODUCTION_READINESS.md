# Production Readiness — What's Left

Rigorous gap analysis after the remediation roadmap (`docs/MASTER_PLAN.md`,
`docs/REAUDIT.md`) and the modularization pass (`docs/ARCHITECTURE.md`).
Direction and sequencing for the open items live in
`docs/IMPROVEMENT_ROADMAP.md`.
Items marked **[gate]** should block a real clinical go-live. Items marked
**[done]** were closed by the follow-up hardening round (R1–R8) or the
approved improvement execution (I0–I17, `docs/IMPLEMENTATION_PLAN.md`);
what remains open is ranked within each category.

## 1. Code & architecture

1. **[done] Typed response contracts.** `api/responses.py` defines pydantic
   response models for the stable endpoints (health, auth, EHR, knowledge
   base, reloads, case create/finalize, transcription); evolving payloads
   use `extra="allow"` so documented keys are guaranteed without freezing
   pipeline output. The typed client landed in I2: `openapi.json` is the
   committed contract, `frontend/src/api/schema.d.ts` is generated from it
   (openapi-typescript), and CI enforces freshness on both sides.
2. **[done] Further decomposition.** `api/routes/ws.py` split from
   `cases.py`; `core/diagnosis/` package (differential / risk / summary)
   replaced the 580-line module (shim kept); frontend gained
   `hooks/useLiveCase` + `LiveAnalysisPanel` (ClinicalInterface 876 → 685).
   Remaining candidate: `InputView`/`ResultsView` screen extraction.
3. **Dependency injection.** State lives in module-global singletons
   (`api/state.py`). Honest at this scale, but an app-factory pattern with
   injected state would allow parallel test isolation and multi-tenant
   configuration.
4. **[done] Consolidate LLM JSON salvage.** One `parse_llm_json` in
   `core/utils.py`, used by all four former copies, with golden-fixture
   tests (`tests/test_llm_parsing.py`).
5. **[done] Template honesty.** `config/prompts/*.j2` render through real
   Jinja2 with `StrictUndefined` (`core.config.render_prompt`).
6. **[done] API versioning.** Every route is dual-mounted at `/` and `/v1`;
   middleware normalizes the prefix so policy is identical on both.
7. **[done] frontend strict mode.** `strict: true` is on and the tree
   compiles clean.

## 2. Testing

1. **[done] End-to-end browser tests.** Playwright covers app boot, the
   degraded quick-analysis flow, the clinical login gate, an axe-core
   accessibility scan, and — closing the former gate item — the live
   voice flow end-to-end with a fake media stream driving the real STT
   pipeline (`e2e/demo/voice.spec.ts`, espeak-generated WAV fixture).
   The first smoke run caught two real production bugs (FormData
   content-type, error-object toast crash).
2. **[done] LLM contract tests.** Record-and-replay fixtures
   (`fixtures/llm/`, `tests/test_llm_replay.py`) pin prompt/parse behavior
   without live keys; `scripts/record_llm_fixtures.py` refreshes them and
   the `live-llm-eval` CI job re-records against live models on demand.
3. **[done] Coverage measurement.** pytest-cov + vitest --coverage run in
   CI; the backend ratchet is set (`--cov-fail-under=50`, raise
   deliberately, never lower) with blind spots named in
   `docs/PERF_BASELINE.md`.
4. **[partly done] Load baseline.** `scripts/ws_load_test.py` measured and
   recorded (`docs/PERF_BASELINE.md`: p95 2.2 s at 5 cases/worker CPU-only).
   Still open: running it on a schedule against a composed stack.
5. **[done] Retrieval quality evals.** `tests/test_retrieval_eval.py`
   asserts topical recall@5 ≥ 0.8 over a labeled query set.

## 3. Security & compliance

1. **[gate] Vendor BAAs before PHI.** Enterprise agreements with Anthropic
   and Google AI (or a de-identification layer, below) before any real
   patient data reaches an LLM endpoint. Tracked in `docs/COMPLIANCE.md`.
2. **[gate] De-identification/PHI-minimization layer** in front of LLM
   egress (scrub names/MRNs/dates from prompts; the deterministic extractor
   already reduces surface, but nothing enforces it).
3. **[partly done] IdP integration.** OIDC authorization-code + PKCE with
   JWKS validation and role mapping is implemented behind `AUTH_MODE=oidc`
   (`core/oidc.py`, I13), and sessions now ride httpOnly cookies with
   logout (`/auth/logout`, I5). Verified against a stub IdP; still open:
   pointing it at the hospital's real provider, revocation/refresh
   semantics, and shortening the 8-hour password-mode TTL.
4. **[done] Supply chain.** Dependabot (pip/npm/actions, weekly, grouped);
   pip-audit and npm-audit are **blocking** with per-ID accepted-findings
   triage in `docs/PERF_BASELINE.md`; image builds gate on a Trivy scan
   (fixable HIGH/CRITICAL fails), publish an SPDX SBOM artifact, and
   cosign-sign the pushed digest once the owner configures
   `COSIGN_PRIVATE_KEY`. fastapi/starlette upgraded past six starlette
   advisories (incl. a Host-header path-check bypass).
5. **[done] Pickle in the RAG store.** The store is JSON
   (`texts.json`/`metas.json`); `.pkl` remains read-compatible only.
6. **In-cluster TLS.** nginx -> backend is plaintext inside the network
   boundary; mTLS or a mesh if the hospital's zoning requires it.
7. **Pen test** before clinical go-live; the internal reviews are strong
   but not independent.

## 4. Operations

1. **[gate→mostly done] Alerting.** `deploy/prometheus-alerts.yml` defines
   error-rate, latency (real p95 via histogram_quantile), LLM
   failure-rate, and token-spend alerts wired to runbook anchors, and the
   stack itself is now deployable config: `docker-compose.observability.yml`
   brings up Prometheus + Alertmanager + Grafana with the backend
   dashboard auto-provisioned (I15). Still open for the gate: running it
   against production (a real Alertmanager receiver) and shipping
   audit/JSON logs to durable storage.
2. **[done] Error tracking.** Sentry integration gated on `SENTRY_DSN`
   (`core/error_tracking.py`, PII off by default); no-op without the DSN.
3. **[partly done] Deploy maturity.** `infra/terraform/` (I16, validated)
   codifies the ECS deployment the manual doc described: VPC, ALB, Fargate
   backend/worker/frontend, EFS, ElastiCache, RDS, scoped IAM, CPU
   target-tracking autoscaling, and a deployment circuit breaker
   (auto-rollback). Still open: CodeDeploy blue/green (deliberately
   deferred, noted in `infra/terraform/README.md`) and a promotion flow.
4. **Backups/DR.** No snapshot policy for EFS (rag_store, caches), the
   users file, or Redis; define RPO/RTO (data criticality notes are in
   `docs/RUNBOOK.md`). Case history now also lives in RDS (I9) — include
   it in the backup policy.
5. **[partly done] HA posture.** Terraform provisions ElastiCache
   multi-AZ with failover plus latency-informed CPU autoscaling; compose
   (dev) still runs a single Redis by design.
6. **[done] Runbooks.** `docs/RUNBOOK.md`: restart/reload, KB rebuild,
   model refresh, and per-alert triage.

## 5. Product & data

1. **[gate→partly done] Real EHR integration.** A FHIR R4 connector with
   SMART Backend Services auth (RFC 7523), LOINC vitals mapping, and
   DocumentReference write-back is implemented behind `EHR_SOURCE=fhir`
   (`core/fhir/`, I12), verified against a stub server. The gate closes
   when it runs against the hospital's real FHIR endpoint with owner
   credentials; until then clinical mode still refuses the synthetic set.
2. **[gate] Clinical validation + regulatory posture.** Advisory framing is
   enforced in code, but a decision-support tool touching diagnosis needs a
   documented clinical evaluation and a CDS-vs-SaMD regulatory assessment
   before real use.
3. **[partly done] Model governance.** `models/registry.yaml` versions
   the imaging/STT/embedding models with eval numbers;
   `scripts/model_gate.py` blocks regressions against the registry; a
   temperature-scaling calibration hook is wired into the imaging head
   (`CXR_CALIBRATION`, identity until fitted); prompts are registered in
   `config/prompts/PROMPTS.md`. Still open: drift monitoring and a
   retraining pipeline (needs production data access).
4. **KB governance.** Corpus is one COVID-era dialogue set + the synthetic
   EHR; provenance, refresh cadence, and clinical review of retrieved
   content are undefined.
5. **[partly done] Accessibility & i18n.** An axe-core scan runs in E2E
   (`e2e/demo/a11y.spec.ts`) and the violations it found are fixed
   (labels, roles, aria-live on the HUD). Still open: a full manual WCAG
   audit (keyboard nav, screen readers) and i18n — STT and UI remain
   English-only.
6. **LICENSE file is missing** while the README claims MIT — the owners
   should add the actual license text (a legal choice, deliberately not
   made by this remediation).

## Suggested sequencing

Two full remediation rounds are done. R1–R8 covered the code-quality
train (JSON salvage, Jinja2, JSON store, decomposition, typed contracts
+ /v1, coverage + retrieval eval + load baseline, Playwright smoke,
runbook + alerts + strict mode). The approved improvement execution
(I0–I17) then closed the machine-checked contract + typed client, the
Vite migration with runtime config, cookie-session auth + CSRF, the
fake-mic voice E2E, property/chaos/mutation testing, real-percentile
metrics + Sentry + deployable observability stack, queue-mode finalize,
event-sourced case persistence with history APIs, model registry +
calibration + benchmarks, LLM replay fixtures + structured outputs,
FHIR/OIDC/secrets scaffolding (stub-verified), validated Terraform, and
blocking supply-chain gates with image scan/SBOM/signing.

What remains needs external parties, credentials, or infrastructure the
repo cannot supply: BAAs and the de-identification layer (the two
remaining hard gates), live FHIR/IdP/secrets against hospital systems,
running the observability stack and Terraform in a real account,
backups/DR policy, in-cluster TLS, pen test, clinical validation, and
the LICENSE decision — gates first, then the enterprise-hardening train.
