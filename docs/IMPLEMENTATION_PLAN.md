# Implementation Plan — Roadmap Execution

**Status: APPROVED (2026-08-22) — decisions recorded below; execution in
progress in package order.**

Approved decisions:

- **D1 → (b)**: Track 1 + Track 2 mock-verified scaffolding.
- **D2 → (a)**: CRA→Vite migration included (I3b).
- **D3 → (a)** (delegated): Postgres via SQLAlchemy — an auditable
  append-only timeline needs a relational store; SQLite-verified here,
  Postgres in compose/prod.
- **D4 → (a)** (delegated): in-process STT worker pool now; the queued
  worker container is designed and flag-gated for a measured rollout —
  best resilience without taking unverifiable latency risk on the live
  path.
- **D5 → (a)** (delegated): print-stylesheet export — it reuses the app's
  own design system, so it is the most consistent by construction.
- **D6 → include**: mutation testing added as a report-only (non-blocking)
  job with the score recorded in `docs/PERF_BASELINE.md`, so it informs
  without being able to flake CI red.

This plan turns `docs/IMPROVEMENT_ROADMAP.md` into ordered, verifiable work
packages. It follows the conventions that worked for the previous rounds
(`docs/MASTER_PLAN.md` P0–P13, then R1–R8): one commit per work package,
every package ends with the full gate suite green, push after each phase.

Work packages are numbered **I0–I17** across three tracks:

- **Track 1 (I0–I10)** — fully implementable and verifiable in the current
  environment (no external accounts, keys, or infrastructure). Starts on
  approval.
- **Track 2 (I11–I17)** — implementable now against mocks/config-as-code,
  but final verification needs owner-provided credentials or
  infrastructure. Each package states exactly what the owner must provide.
- **Track 3 (E1–E6)** — organizational/external items the plan can define
  but not execute (BAAs, pen test, clinical validation, licensing).

**Verification environment constraints** (each package's "Verify" is
written against these honestly): no Docker daemon (compose changes are
authored + config-validated, not container-run), no LLM API keys (LLM
paths verified in degraded mode + with recorded fixtures), no GPU, CPU-only
inference, Chromium available for Playwright.

**Gates** (run at the end of every package): backend
`pytest -q` + `ruff check`, frontend `tsc --noEmit` + unit tests +
production build, Playwright `e2e/demo` + `e2e/clinical`, plus any gate the
package itself adds.

**Effort scale**: S ≈ ≤half a session, M ≈ one session, L ≈ multiple
sessions. ("Session" = one focused working block in this environment.)

---

## Decision points for review

Approve as-is, or amend any of these. Recommendations are marked ►.

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| D1 | Execution scope on approval | (a) Track 1 only; (b) ► Track 1 + Track 2 mock-verified scaffolding (FHIR/OIDC/Sentry code behind flags, verified against mocks) | (b) — the scaffolding is the long-lead item; mocks make it real enough to review |
| D2 | CRA→Vite migration (I3b) | (a) ► Include now (clears 28 audit findings, faster CI); (b) defer to its own round | (a), sequenced after the generated client so types catch breakage |
| D3 | Case persistence store (I9) | (a) ► Postgres via SQLAlchemy, SQLite-verified here, PG in compose/prod; (b) stay Redis + snapshots | (a) — Redis snapshots don't give an auditable timeline |
| D4 | STT decoupling depth (I4b) | (a) ► In-process worker pool now, queued-worker container designed but flag-gated; (b) full worker container now | (a) — the live path's latency budget deserves a measured rollout |
| D5 | PDF export mechanism (I8) | (a) ► Print-stylesheet (client-side, zero deps); (b) server-side WeasyPrint | (a) first; (b) only if pixel-fidelity is required |
| D6 | Mutation testing (I7) | (a) report-only optional job; (b) ► skip for now (slow, low signal at current suite size) | (b) |

---

## Track 1 — in-environment (starts on approval)

### I0 — Repo hygiene quick wins (S)

**Goal**: close the zero-risk governance items so they stop appearing in
audits.
**Changes**: `CODEOWNERS`, `.github/pull_request_template.md`,
`docs/adr/0001-record-architecture-decisions.md` (+ ADRs back-filling the
big standing decisions: modular monolith, dual-mount /v1, demo/clinical
switch), `CHANGELOG.md` seeded from the P/R/I history. LICENSE remains the
owner's call — the plan does **not** add one.
**Verify**: gates; PR template renders.
**Risk**: none.

### I1 — Truth-in-UI + degraded-mode visibility (S)

**Goal**: the UI never claims capabilities the deployment doesn't have.
**Changes**:
- `/knowledge_base/mode` returns real KB facts (source files, chunk count,
  built-at from `rag_store/config.json`) instead of the hardcoded
  "UpToDate/PubMed / 2024-01-01" fiction; `KnowledgeBaseToggle` renders
  those real sources.
- `/health` gains `llm: {anthropic: bool, gemini: bool}` (booleans only —
  never key material); frontend shows a persistent "AI assistance
  degraded" banner when both are false, and a smaller chip when only the
  fallback is available.
**Verify**: gates + new unit tests + an E2E assertion that the banner
appears in this (keyless) environment.
**Risk**: low; response-model additions are additive (`extra="allow"`).

### I2 — Contract & release decoupling (M)

**Goal**: machine-checked API contract; halves release independently.
**Changes**:
- `scripts/export_openapi.py` dumps the schema to `openapi.json` (checked
  in, CI-verified as up-to-date so drift fails the build).
- Generated TypeScript client (openapi-ts) in `frontend/src/api/gen/`;
  `services/api.ts` becomes a thin layer (auth interceptors, error
  normalization) over generated calls; hand-written `any` wrappers deleted
  incrementally (health/auth/EHR/cases first, uploads last).
- Contract-test CI job: schemathesis fuzzes a local uvicorn against the
  exported schema (demo mode; auth endpoints included); any 500 it finds
  is fixed in this package.
- Path-filtered CI: backend jobs skip on frontend-only diffs and vice
  versa; `build-and-push` splits into two independently-triggered image
  builds with independent tags.
**Verify**: gates + schemathesis clean + a deliberate schema drift failing
the freshness check.
**Risk**: medium (wide but mechanical frontend churn); mitigated by the
E2E suite and incremental replacement.
**Depends on**: I1 (so the schema it freezes includes the new fields).

### I3 — Runtime config (a) and CRA→Vite (b) (M+L)

**Goal**: one frontend artifact runs against any backend; modern toolchain.
**Changes**:
- (a) nginx entrypoint templates `window.__MEDISENSE_CONFIG__` into a
  served `config.js`; `src/config/api.ts` resolution order becomes runtime
  config → build-time env → same-origin. E2E stops rebuilding per backend
  URL.
- (b) Vite + vitest migration: `index.html` to root, `VITE_*` env names
  (largely moot after (a)), jest→vitest (jest-compatible API; the 9 unit
  tests port as-is), CRA removed, E2E static server points at `dist/`,
  CI updated. Expected side effect: the 28 remaining `npm audit` findings
  (all react-scripts transitives) clear.
**Verify**: gates (vitest replacing jest) + both E2E suites + `npm audit`
delta recorded in `docs/PERF_BASELINE.md`.
**Risk**: highest of the frontend packages — (b) lands as its own commit
with (a) already green, so rollback is one revert.
**Depends on**: I2 (typed client catches migration breakage).

### I4 — Compute decoupling: job queue (a) and STT pool (b) (M)

**Goal**: slow work off the request path; STT stops competing with the
event loop.
**Changes**:
- (a) arq worker over the existing Redis: `worker/` module +
  `finalize_report` job; `POST /api/case/{id}/finalize` enqueues and
  returns a job id; `GET /api/case/{id}/report` polls; WS pushes a
  `report_ready` frame. Synchronous path retained behind
  `FINALIZE_MODE=inline` for single-container deployments. Compose gains a
  `worker` service (authored; container-run verification deferred — no
  Docker here).
- (b) STT executor becomes a sized process pool (`STT_WORKERS`, default
  scaled to CPU count); the queued-worker-container design is documented
  in `docs/ARCHITECTURE.md` and flag-gated for a later measured rollout
  (per D4).
**Verify**: gates + new job-lifecycle tests (arq test harness, Redis
optional via fakeredis) + `scripts/ws_load_test.py` re-run; baseline table
updated.
**Risk**: medium — finalize gains a state machine; inline mode is the
rollback.

### I5 — Cookie-session auth (M)

**Goal**: tokens out of `localStorage`; the BFF security benefit without a
BFF.
**Changes**: `/auth/login` sets an httpOnly `SameSite=Strict` session
cookie (bearer still accepted for API clients); middleware resolves cookie
→ bearer in that order; CSRF double-submit token for cookie-authenticated
mutating requests; `/auth/logout`; WS-ticket flow unchanged (cookie
session mints tickets). Frontend: `withCredentials`, localStorage token
removed in cookie mode, CSRF header wiring in the (now generated) client
layer.
**Verify**: gates + extended clinical-auth tests (cookie flow, CSRF
negative cases, mixed bearer/cookie) + clinical E2E updated to assert no
token in localStorage.
**Risk**: medium — auth changes get the adversarial-review treatment (as
in P8): explicit negative tests for CSRF, cookie scope, and downgrade
paths before push.

### I6 — Observability internals (M)

**Goal**: real percentiles; error tracking wired; tracing scaffolded.
**Changes**:
- `core/metrics.py` reimplemented on `prometheus_client` (Histogram with
  latency buckets, Counter, same `inc/observe/timed` call-site API);
  `/metrics` serves `generate_latest`; `deploy/prometheus-alerts.yml`
  rewritten to `histogram_quantile` p95 rules (replacing the mean-based
  approximations).
- Sentry SDK (backend + frontend) behind `SENTRY_DSN` — inert without the
  env var; verified via transport stub in tests.
- OpenTelemetry request/stage/LLM spans behind `OTEL_EXPORTER_OTLP_ENDPOINT`
  — no-op by default.
**Verify**: gates + exposition-format tests + alert YAML validated + a
histogram-bucket assertion in the metrics tests.
**Risk**: low-medium; the emit API is preserved so call sites don't churn.

### I7 — Testing depth (M)

**Goal**: the suite catches what unit tests structurally can't.
**Changes**:
- Fake-mic E2E: Chromium launched with
  `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream
  --use-file-for-fake-audio-capture=<wav>`; a committed speech WAV fixture
  if one can be sourced/synthesized here, else the test asserts the full
  plumbing (worklet → PCM frames → WS → flush → HUD update) with the
  transcript-content assertion skip-guarded on fixture presence — the
  honest fallback is stated in the test.
- Property-based tests (hypothesis) for `parse_llm_json`, `chunk_words`,
  `chunk_dialogue`, the extractor's negation/duration parsing.
- Chaos tests: Redis unreachable, LLM raising, empty retriever — each
  asserting the documented degraded behavior, not a 500.
- Coverage: CI records the light-set baseline for two runs, then a
  follow-up commit sets `--cov-fail-under` two points beneath it (ratchet
  raised deliberately thereafter). Mutation testing skipped per D6.
**Verify**: the new suites themselves + gates.
**Risk**: low; purely additive.

### I8 — Product UX round (M)

**Goal**: clinician-facing polish that doesn't need persistence.
**Changes**: print-stylesheet PDF export of the report view (per D5);
accept/dismiss controls on coach questions (events POSTed to a new
`/api/case/{id}/feedback` endpoint — stored in the case store now, the
durable timeline in I9); confidence-over-time sparkline in the HUD
(dataviz conventions); ARIA live regions for streaming HUD updates,
keyboard navigation pass, axe-core automated a11y check added to the demo
E2E.
**Verify**: gates + axe-core clean on the three main views + new endpoint
tests.
**Risk**: low.

### I9 — Case persistence: event-sourced timeline (L)

**Goal**: a durable, auditable record of what the clinician saw; the
substrate for history views and the feedback loop.
**Changes** (per D3): SQLAlchemy + Alembic; tables `cases`,
`case_events` (append-only: utterances, HUD snapshots, questions
shown/dismissed, finalize), `reports`; `CASE_STORE=postgres` backend
joining memory/redis behind the existing `core/case_store` interface; WS
ingest and finalize write events; new endpoints `GET /v1/cases` (filter by
patient/date) and `GET /v1/cases/{id}/timeline`; retention config;
audit-log alignment (events carry request ids). Case-history view in the
frontend (list + timeline read-only render).
**Verify**: gates + the full suite against SQLite; Alembic
migration-roundtrip test; PG-specific verification explicitly deferred to
a Docker-capable environment and tracked as a checklist item in this doc.
**Risk**: the largest Track 1 package; store stays opt-in via env until
PG-verified, so demo/clinical behavior is unchanged by default.
**Depends on**: I4a (worker writes report events).

### I10 — Clinical-ML groundwork (M)

**Goal**: everything model-improvement needs that doesn't need data/GPU.
**Changes**: calibration scaffolding (temperature-scaling module with
tests on synthetic logits); model-registry metadata format
(`models/registry.yaml`: checkpoint hash, eval metrics, date) enforced at
imaging load; eval-gate harness that fails if a candidate checkpoint's
recorded metrics regress; embedding-swap experiment — pull a medical
sentence-embedding model through the proxy if reachable, rebuild the KB in
a side directory, run the retrieval eval comparatively, and record the
result (adopt only if recall improves); STT model made config-driven
(`STT_MODEL`) with a benchmark script comparing tiny.en vs. a distil
model on latency + WER over committed samples.
**Verify**: gates + the new harness tests + recorded comparison numbers in
`docs/PERF_BASELINE.md`.
**Risk**: low; experiments land as data, adoption is a separate decision.

---

## Track 2 — mock-verified now, owner-completed later

Each package is built and tested against mocks/stubs in-environment (if D1
= option b); the **Owner provides** line is what converts it to live.

### I11 — LLM eval harness + structured outputs + caching (M)

Record/replay fixtures (recording script needs keys; replay tests run
keyless), golden conversations per path, prompt versioning; structured
outputs on the Claude paths with `parse_llm_json` demoted to fallback;
prompt restructure for an append-only cacheable prefix with cache-hit
assertions in the recorded fixtures.
**Owner provides**: API keys for one recording session (or adds them as CI
secrets for an optional live-eval job).

### I12 — FHIR connector (SMART-on-FHIR) (L)

`core/fhir/` client (OAuth2 SMART launch, Patient/Condition/Observation/
MedicationRequest → internal EHR shape mapping, DocumentReference
write-back for final reports); verified against recorded fixtures and a
stub FHIR server in tests; `EHR_SOURCE=fhir` joins the existing synthetic
loader behind the same interface, keeping the clinical-mode
synthetic-refusal guarantees intact.
**Owner provides**: Epic (or other) sandbox app registration — client id,
redirect URI, sandbox tenant.

### I13 — OIDC/SSO (M)

Authlib-based OIDC login alongside file-users (`AUTH_MODE=oidc`); token
refresh, revocation on logout, TTL from the IdP; role mapping from claims;
verified against an in-test stub IdP.
**Owner provides**: hospital IdP metadata/registration.

### I14 — Secrets manager (S)

`core/secrets.py` resolution order: AWS Secrets Manager → env → file;
moto-based tests.
**Owner provides**: AWS account wiring at deploy time.

### I15 — Observability deployment (M)

Prometheus + Alertmanager + Grafana provisioning as code (compose overlay
+ ECS task definitions + dashboard JSON committed); scrape auth via a
service token for clinical mode.
**Owner provides**: the environment to run it in (verification here stops
at config validation — no Docker daemon).

### I16 — Terraform for ECS (L)

The IaC that `aws_ecs_deployment.md` describes: VPC/ALB/ECS
services/EFS/ElastiCache/ECR/IAM, blue-green via CodeDeploy, autoscaling
keyed to the latency metrics; `terraform fmt`/`validate` here if the
binary is obtainable, `plan`/`apply` owner-side.
**Owner provides**: AWS account, state backend, region decisions.

### I17 — Supply-chain completion (S)

Trivy image scan + syft SBOM + cosign signing in CI; the advisory audit
job flips to blocking after a triage pass documents accepted findings.
**Owner provides**: registry credentials for the signing step.

---

## Track 3 — owner-led (plan defines the deliverable)

| # | Item | Deliverable to check off |
|---|------|--------------------------|
| E1 | Vendor BAAs (LLM providers) | Signed agreements on file; noted in `docs/COMPLIANCE.md` before any PHI egress |
| E2 | De-identification policy | Choice of scrubbing engine + policy for what may reach an LLM; then implemented as a Track 1-style package in front of `core/llm_client` |
| E3 | Pen test | Independent report + remediation round |
| E4 | Clinical validation + CDS-vs-SaMD assessment | Documented study protocol, results, and regulatory determination |
| E5 | KB licensing | Licensed guideline content feeding §2 of the roadmap (until then the UI claims only what it has — enforced by I1) |
| E6 | LICENSE file | Owner's legal choice; README's MIT claim reconciled |

---

## Sequencing & dependency graph

```
I0 ─┐
I1 ─┴─► I2 ─► I3a ─► I3b
              │
I4a ─► I4b    │
  └────────► I9 ─► (feedback loop lives here)
I5  (independent)
I6  (independent)
I7  (after I3b so tests target the final toolchain)
I8  (after I2; feedback endpoint joins I9's timeline when it lands)
I10 (independent)
I11–I17 interleave once their mocks/config are reviewable; live
completion tracks the "Owner provides" items.
```

Proposed execution order for the next sessions:
**I0 → I1 → I2 → I3a → I3b → I6 → I4 → I5 → I7 → I8 → I10 → I9**, with
Track 2 scaffolding (I11–I14) interleaved where waiting on review. Roughly
4–6 working sessions for Track 1; Track 2 scaffolding ~2–3 more.

## Definition of done (per package and overall)

- Every package: gates green, one commit, honest verification note where
  the environment limits it (no silent "verified" for container-run or
  live-key behavior), `docs/` updated where behavior changed, pushed to
  `claude/medisense-repo-setup-560vwg`.
- Overall: `docs/PRODUCTION_READINESS.md` re-statused at the end (as after
  R8), a final re-audit pass over everything Track 1 changed, and an
  updated `docs/PERF_BASELINE.md` (load test, coverage, audit counts,
  npm-audit delta from Vite).

## Coverage matrix (roadmap § → packages)

| Roadmap section | Packages |
|---|---|
| 1 Clinical intelligence | I10, I11; fine-tune itself needs data+GPU (owner: dataset access; then a dedicated round) |
| 2 KB & retrieval | I1 (truth-in-UI), I10 (embedding experiment), E5 (corpus) |
| 3 LLM layer | I11 (structured outputs, caching, evals), E2 (de-id) |
| 4 Data & EHR | I9 (persistence + feedback), I12 (FHIR) |
| 5 Security gates | I5, I13, I14, I17, E1–E3 |
| 6 Operations | I4, I6, I15, I16 |
| 7 Decoupling | I2, I3, I4, I5 (deferred: repo split, Node tier — unchanged) |
| 8 Frontend & UX | I3, I8 |
| 9 Testing depth | I2 (schemathesis), I7 |
| 10 Governance | I0, I10 (model registry), E4, E6 |

---

**To approve**: confirm the decision points (D1–D6, or amendments) and say
go. Implementation begins at I0 and proceeds in the order above, with the
same per-package commit/verify/push discipline as the previous rounds.
