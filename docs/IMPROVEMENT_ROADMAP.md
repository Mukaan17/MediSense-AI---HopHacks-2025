# Improvement Roadmap

Direction and sequencing for taking the platform from "clean and hardened"
to genuinely production-grade. This complements `docs/PRODUCTION_READINESS.md`
(the gap register — what is open vs. closed) with *how to get there and in
what order*. Baseline: the R1–R8 hardening round is complete (see
`docs/PRODUCTION_READINESS.md` for what that closed).

The framing: the remaining gains are less about code cleanliness and more
about clinical quality, data access, decoupling, and operational trust.
★ marks the highest-leverage item in each area.

---

## 1. Clinical intelligence — the product's actual value

- **Imaging head** ★ — the BiomedCLIP head (val macro AUROC 0.78) is
  demo-grade. Fine-tune on CheXpert/MIMIC-CXR with a held-out eval set,
  calibrate the probabilities (temperature scaling — raw scores currently
  feed fusion as if they were probabilities), set per-class thresholds, and
  put the checkpoint behind a versioned registry with a regression-eval
  gate so a model swap cannot silently degrade.
- **Fusion/evidence engine** — weights are hand-tuned. Once labeled
  outcomes exist, learn them; report calibrated confidence with
  uncertainty rather than a bare score. The XAI panel is only as honest as
  the numbers feeding it.
- **Coach questions** — `info_gain` is whatever the LLM claims. Compute
  actual expected information gain against the live differential so
  question ranking is principled. The prescriptive-language guardrail is
  regex; for a safety-critical filter, add a second-model check behind it.
- **Live STT** — `tiny.en int8` is fast but weak on medical vocabulary,
  and speaker labels come from the client. Move to a distil/medium model
  with domain hotwords, add server-side diarization, and plan for
  multilingual support (corpus and UI are English-only).

## 2. Knowledge base & retrieval

- **Corpus** ★ — one COVID-era dialogue set plus synthetic EHR is the
  thinnest part of the platform. License or curate real guideline content,
  with provenance, refresh cadence, and clinical review sign-off per
  ingestion.
- **Truth-in-UI** — the knowledge-base toggle advertises "UpToDate /
  PubMed" sources that do not exist, and `/knowledge_base/mode` returns a
  hardcoded `last_updated`. A clinical tool claiming sources it doesn't
  have is a credibility bug; fix before adding features. (Small — a
  ridealong, not a project.)
- **Retrieval quality** — swap general-purpose MiniLM for a medical
  embedding model; add hybrid BM25+dense retrieval; use the chunk metadata
  (condition/age/sex) as query-time filters. Grow the recall@5 tripwire
  (`tests/test_retrieval_eval.py`) into a real labeled benchmark with
  rerank-gain measurement.

## 3. LLM layer

- **Structured outputs instead of parse-and-salvage** — the API supports
  schema-constrained responses and strict tool schemas; adopting them
  makes `core.utils.parse_llm_json` a fallback rather than the contract
  (validation failures become impossible instead of salvaged).
- **Prompt caching** — the live pipeline re-sends a growing conversation
  on every utterance. Restructure prompts so history is an append-only
  prefix, add cache breakpoints, and verify cache reads in the usage
  metrics; a direct latency and cost cut on the hottest path.
- **Model registry hygiene** — `config/models.yaml` is the right
  abstraction; revisit the pins periodically. Current-generation models
  offer thinking/effort controls that map well onto the live-vs-final
  split (low effort for the coach, high for the final report).
- **Eval harness** ★ — record/replay golden conversations per path
  (coach, finalize, structured diagnosis), versioned prompts, offline
  evals in CI (the batch API halves the cost of running them). Today a
  prompt regression is invisible until a demo.
- **De-identification before egress** — a scrubbing layer (Presidio-style)
  in front of every LLM call, enforced with tests. Both a compliance gate
  and defense in depth.

## 4. Data & EHR — the existential gap

- **FHIR connector** ★ — clinical mode correctly refuses synthetic EHR,
  which means clinical mode has *no* EHR. SMART-on-FHIR against an Epic
  sandbox is the single biggest unlock; write-back of the final report as
  a DocumentReference closes the loop.
- **Case persistence** — cases are ephemeral by design (memory/Redis). A
  clinical product needs a durable record of what the clinician was shown:
  an event-sourced case timeline in Postgres fits the utterance-stream
  model, survives restarts, and — critically — enables the **feedback
  loop**: clinicians accepting/dismissing questions and diagnoses becomes
  labeled data for everything in section 1.

## 5. Security & compliance (go-live gates)

BAAs with the LLM vendors; OIDC/hospital SSO with revocation, MFA, and a
TTL well under the current 8 hours; a secrets manager instead of env
files; per-user (not just per-IP) rate limiting, trusting
`X-Forwarded-For` only from the known proxy; Trivy image scanning + SBOM +
signed images, then making the advisory audit CI job blocking; mTLS
in-cluster; CSP headers; WORM storage for the audit log; an independent
pen test. None are individually hard — they are gates because nobody
inside the project can waive them.

## 6. Operations

- **Deploy the observability stack** ★ — `deploy/prometheus-alerts.yml`
  exists but nothing evaluates it. Stand up Prometheus/Alertmanager plus a
  dashboard-as-code, and replace the hand-rolled `core/metrics.py` with
  `prometheus_client` histograms — the alert rules approximate p95 with
  means precisely because the current exporter cannot do quantiles.
- Error tracking (Sentry or equivalent) on both halves; OpenTelemetry
  traces (request → pipeline stage → LLM call spans); Terraform for the
  ECS deploy with blue/green and auto-rollback on error rate; scheduled
  synthetic E2E and a nightly load run against staging
  (`docs/PERF_BASELINE.md` holds the budgets); backups/DR with stated
  RPO/RTO; SLOs with error budgets.
- **Finalize-report as a background job** — currently request-scoped, so a
  slow LLM call ties up a worker and a timeout loses the work. Queue it
  (see §7 compute decoupling), poll or notify over the existing WS.
- **WS resilience** — heartbeats, reconnect-with-resume (the client
  reconnects cold today), documented sticky-session requirements for
  multi-worker deployments.

## 7. Architecture & decoupling

The platform is already *deployment*-decoupled: two images
(`Dockerfile.cpu`, `Dockerfile.frontend`), an HTTP+WS boundary, a
`/v1`-versioned API with typed response models, CORS + WS-ticket auth that
works cross-origin. The remaining coupling is subtler, and the two popular
"big" decouplings (repo split, Node tier) are mostly the wrong ones here.

### What is still coupled

- **Contract coupling** — the frontend talks to the API through ~500 lines
  of hand-written axios wrappers typed `any`. Nothing machine-checks that
  the two sides agree; the E2E suite is the only tripwire.
- **Build-time coupling** — `REACT_APP_API_URL` is baked into the CRA
  build, so one frontend artifact is married to one backend URL.
- **Release coupling** — CI's `build-and-push` rebuilds and ships both
  images on any push; a CSS change redeploys the backend.
- **Compute coupling** — STT, cross-encoder rerank, imaging, and the
  finalize report all run inside the API process; load on one degrades
  all. This is the coupling that actually hurts at hospital scale.

### Contract decoupling ★ (the valuable one)

Generate the TypeScript client from the OpenAPI schema (openapi-ts) into a
`packages/api-client`, delete the hand-written wrappers, and add contract
tests in CI (schemathesis fuzzing the backend against its own schema; the
frontend compiling against the generated types). Combined with the `/v1`
mount, this is what genuinely lets the halves evolve and deploy
independently: a breaking backend change fails the frontend type-check in
CI instead of failing in a clinic.

Pair with **runtime config instead of build-time config**: nginx serves a
small `config.js` (or templates `window.__CONFIG__` into `index.html` at
container start) so one frontend build works against any backend. That
removes the last hard link between a frontend artifact and a specific
backend deployment.

### Release decoupling

Path-filtered CI: frontend-only changes skip the backend jobs and image
build, and vice versa; two independently tagged, independently deployable
images. Optionally formalize with a workspace layout (`apps/backend`,
`apps/frontend`, `packages/api-client`) so the structure states the
architecture.

### Compute decoupling (the backend half of the question)

The `core`-never-imports-`api` rule was built as this seam, so extraction
is cheap:

1. **STT worker first** — faster-whisper runs on a single-worker executor
   inside the API process; transcription bursts and HTTP/WS latency share
   a CPU budget. Move it behind the existing Redis (arq/celery) or a
   dedicated worker container consuming PCM jobs. Clearest per-service
   scaling win: STT scales with concurrent *speakers*, the API with
   concurrent *cases*.
2. **Finalize-report queue** — same worker infrastructure (see §6).
3. **Rerank/retrieval service** — only when the latency metrics demand it;
   the cross-encoder is the pipeline's hog and a separate inference
   service could scale (or GPU) independently. Until then a process pool
   inside the backend suffices.

Explicitly **not microservices**: at this team size, a modular monolith
with worker processes gets the isolation without the distributed-systems
tax. The module boundaries are drawn so any component can be lifted out
later without a rewrite.

### Deliberately deferred

- **Repo split (polyrepo)** — buys independence not yet needed and costs
  what is used daily: atomic cross-contract commits, the shared E2E suite
  (which caught two production bugs precisely because it spans both
  halves), one CI story. Revisit when separate teams own separate release
  cadences.
- **Node tier (Next.js/SSR/BFF)** — this is an authenticated clinical
  tool behind a login, not a content site; the live path is WebSockets,
  which a Node middle-hop makes worse. The one legitimate BFF argument is
  auth: the JWT lives in `localStorage` and is XSS-stealable, and httpOnly
  cookie sessions are the fix — but FastAPI can set the cookie itself and
  the nginx same-origin deployment already supports it. That is a backend
  feature, not a new tier. Reach for a Node/SSR layer only if the roadmap
  adds a content-like surface (patient-facing pages, docs portal); do the
  CRA→Vite migration first regardless.

## 8. Frontend & UX

- **CRA → Vite** ★ — clears the 28 remaining audit findings (all
  react-scripts build-time transitives), speeds builds, modernizes the
  toolchain in one move.
- Generated typed client (see §7), React Query for data fetching, a state
  machine for the live-case lifecycle (the pending-utterance queue and WS
  states are already state-machine-shaped).
- **Product UX**: case history view, PDF export of reports, a visible
  degraded-mode banner (missing LLM keys currently degrade silently — a
  clinician cannot tell), confidence-over-time in the HUD, accept/dismiss
  on coach questions (feeding the §4 feedback loop).
- **Cookie-session auth** (see §7) replacing localStorage tokens.
- Accessibility: WCAG audit, ARIA live regions for the streaming HUD,
  keyboard navigation; i18n; a tablet/bedside layout.

## 9. Testing depth

The remaining E2E gate is the fake-mic voice flow
(`--use-fake-device-for-media-stream` + a WAV fixture through the worklet
→ WS → HUD). Beyond that: schemathesis fuzzing driven by the OpenAPI
schema, property-based tests for the parsers/chunker, mutation testing to
validate the suite itself, a coverage ratchet, and chaos cases (Redis
down, LLM 500s, slow KB volume) asserting graceful degradation.

## 10. Governance & process

Model cards and drift monitoring for the imaging head; a retraining
pipeline; the CDS-vs-SaMD regulatory assessment and a documented clinical
validation study — the true gate for real use; no amount of engineering
substitutes for it. Repo-level: the missing LICENSE (owner's legal call),
CODEOWNERS, branch protection, ADRs for the big decisions, a changelog.

---

## Sequencing

1. **Trust gates** — FHIR connector + case persistence, de-id + BAAs,
   OIDC + cookie sessions. Without these, clinical mode is a well-secured
   shell.
2. **Operate-ability** — observability stack deployed, error tracking,
   Terraform. You cannot run what you cannot see.
3. **Decoupling train** (cheap, and it de-risks everything after it) —
   path-filtered CI and independent image deploys; generated typed client
   + contract tests; runtime config injection; CRA→Vite; then the STT
   worker + finalize queue over the existing Redis.
4. **Clinical quality** — imaging fine-tune + calibration, medical
   embeddings + real corpus, LLM eval harness. This is where the product's
   value lives.
5. **The feedback loop** — persistence → clinician labels → model
   improvement, which compounds everything in step 4.
6. **Ridealongs** folded into normal work — truth-in-UI fixes,
   `prometheus_client` histograms, structured outputs, accessibility
   passes.
7. **Deferred until the need arrives** — repo split, Node/SSR tier,
   microservices.

Items achievable without external accounts or infrastructure (and
therefore good next sessions in this environment): the decoupling train's
first four steps, the fake-mic E2E, histograms, structured outputs on the
Claude path, cookie-session auth, and the truth-in-UI fixes.
