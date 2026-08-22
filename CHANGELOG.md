# Changelog

Notable changes by engineering round. Package-level detail lives in the
plan documents (`docs/MASTER_PLAN.md`, `docs/IMPLEMENTATION_PLAN.md`) and
per-commit messages.

## Roadmap execution (I0–I17), 2026-08

- I0: CODEOWNERS, PR template, ADRs (`docs/adr/`), this changelog.
- I1: truth-in-UI — the KB panel and health endpoint report real store
  facts (doc count, built-at, LLM availability); degraded-mode banner.
- I2: machine-checked API contract — committed `openapi.json`, generated
  `frontend/src/api/schema.d.ts`, freshness gates on both sides, and a
  schemathesis fuzz job; CI rebuilt with path filters and split image
  builds gated on their own tests.
- I3: runtime config injection (one frontend build, any backend) and the
  CRA → Vite migration (build ~40 s → ~2 s, npm audit to 0, vitest).
- I4: finalize-report job queue (arq, `FINALIZE_MODE=queue`, inline
  fallback) + sized live-STT worker pool (`STT_WORKERS`).
- I5: httpOnly cookie sessions with double-submit CSRF replace
  localStorage tokens; Bearer stays for API clients; logout + `/auth/me`.
- I6: real observability internals — prometheus_client histograms
  (honest percentiles), OTel span scaffold, Sentry gated on `SENTRY_DSN`;
  alert rules moved to `histogram_quantile`.
- I7: testing depth — fake-mic Playwright voice E2E driving the real STT
  pipeline, property-based tests (hypothesis), chaos tests (which found
  and fixed an unhandled store-outage 500 → explicit 503), mutation
  baseline, coverage ratchet.
- I8: product UX — question feedback capture, confidence sparkline,
  aria-live HUD, print-stylesheet PDF export, axe-core a11y gate.
- I9: event-sourced case persistence (SQLAlchemy: snapshots + append-only
  events + reports; alembic; retention cron; history + timeline APIs and
  a case-history view).
- I10: clinical-ML groundwork — model registry + eval gate, temperature
  calibration hook, STT/embedding benchmarks recorded.
- I11: LLM structured-output modes (Claude JSON schema; Gemini JSON mime),
  prompt-cache hooks, record-and-replay fixture tests, prompt registry,
  on-demand live-eval CI job.
- I12: SMART-on-FHIR R4 connector behind `EHR_SOURCE=fhir`
  (backend-services JWT, LOINC vitals mapping, DocumentReference
  write-back), stub-verified.
- I13: OIDC authorization-code + PKCE scaffolding behind `AUTH_MODE=oidc`,
  stub-IdP-verified.
- I14: managed secret resolution (AWS Secrets Manager → env → `_FILE`),
  hydrated at startup.
- I15: observability deployment as code — compose overlay with
  Prometheus, Alertmanager, Grafana + provisioned dashboard.
- I16: validated Terraform for the ECS deployment (VPC, ALB, Fargate
  services + worker, EFS, ElastiCache, RDS, scoped IAM, autoscaling,
  deployment circuit breaker).
- I17: supply-chain completion — blocking pip/npm audits with per-ID
  triage, Trivy image scan + SPDX SBOM + cosign signing in the build
  lane; fastapi/starlette upgraded past six starlette advisories (incl.
  a Host-header path-check bypass).

## Hardening round (R1–R8), 2026-08

- One `parse_llm_json` with golden-fixture tests replaces four copy-pasted
  LLM JSON salvage blocks.
- Prompt templates render through real Jinja2 (`StrictUndefined`).
- RAG store migrated pickle → JSON (deserialization class removed).
- Decomposition round 2: `api/routes/ws.py` split from `cases.py`,
  `core/diagnosis/` package, frontend `useLiveCase` hook +
  `LiveAnalysisPanel`.
- Typed response models + `/v1` dual-mount with prefix-normalized policy.
- Coverage in CI, Dependabot, advisory pip-audit/npm-audit job,
  python-jose CVE upgrade, retrieval recall@5 eval, WS load baseline
  (`docs/PERF_BASELINE.md`).
- Playwright E2E smoke (demo + clinical) — first run caught and fixed two
  production bugs (FormData content-type; error-object toast crash).
- Runbook, Prometheus alert rules, `llm_errors` metric, frontend
  `strict: true`.

## Remediation roadmap (P0–P13), 2026-08

- RAG chunking + metadata; cross-encoder re-ranking.
- True token streaming for the live coach; deep final report; model
  routing via `config/models.yaml` with fallback.
- Server-side live STT (AudioWorklet PCM → `/ws/transcribe`, energy VAD).
- Demo/clinical mode switch; JWT auth with WS tickets; security
  middleware (request IDs, upload caps, rate limiting, audit log).
- Redis-backed case store option; CI gates; CPU Docker + compose + ECS
  deployment docs; `/metrics`; compliance notes.

## Pre-remediation (hackathon baseline), 2025-09

- Original HopHacks build: FastAPI monolith, CRA frontend, FAISS KB,
  BiomedCLIP imaging, WhisperX voice, Gemini-based advisory pipeline.
