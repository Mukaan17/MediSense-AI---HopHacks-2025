# Production Readiness — What's Left

Rigorous gap analysis after the remediation roadmap (`docs/MASTER_PLAN.md`,
`docs/REAUDIT.md`) and the modularization pass (`docs/ARCHITECTURE.md`).
Items marked **[gate]** should block a real clinical go-live. Items marked
**[done]** were closed by the follow-up hardening round (R1–R8); what
remains open is ranked within each category.

## 1. Code & architecture

1. **[done] Typed response contracts.** `api/responses.py` defines pydantic
   response models for the stable endpoints (health, auth, EHR, knowledge
   base, reloads, case create/finalize, transcription); evolving payloads
   use `extra="allow"` so documented keys are guaranteed without freezing
   pipeline output. Next increment: generate a typed client (openapi-ts).
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

1. **[gate→partly done] End-to-end browser tests.** Playwright smoke now
   covers app boot, the degraded quick-analysis flow, and the clinical
   login gate (`frontend/e2e/`, CI job `test-e2e`) — its first run caught
   two real production bugs (FormData content-type, error-object toast
   crash). Still open for the full gate: the live voice flow with a fake
   media stream (`--use-fake-device-for-media-stream` + WAV fixture).
2. **LLM contract tests.** Claude/Gemini calls are mocked or degraded in
   CI; record-and-replay fixtures (VCR-style) for one golden conversation
   per path would catch prompt/parse regressions without live keys.
3. **[done] Coverage measurement.** pytest-cov + jest --coverage run in CI;
   baseline 56% backend lines with blind spots named in
   `docs/PERF_BASELINE.md`. Ratchet still to be set once CI numbers settle.
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
3. **IdP integration.** File-based users + JWTs cannot be revoked; front an
   OIDC provider (hospital SSO), add refresh/logout semantics, and shorten
   the 8-hour TTL.
4. **[partly done] Supply chain.** Dependabot (pip/npm/actions, weekly,
   grouped) + an advisory pip-audit/npm-audit CI job are in place;
   python-jose upgraded past its CVEs and npm criticals cleared. Still
   open: image scanning (Trivy), SBOM, and making the audit job blocking.
5. **[done] Pickle in the RAG store.** The store is JSON
   (`texts.json`/`metas.json`); `.pkl` remains read-compatible only.
6. **In-cluster TLS.** nginx -> backend is plaintext inside the network
   boundary; mTLS or a mesh if the hospital's zoning requires it.
7. **Pen test** before clinical go-live; the internal reviews are strong
   but not independent.

## 4. Operations

1. **[gate→partly done] Alerting.** `deploy/prometheus-alerts.yml` defines
   error-rate, latency, LLM failure-rate (new `llm_errors` metric), and
   token-spend alerts wired to runbook anchors. Still open for the gate:
   actually deploying Prometheus/Alertmanager + a dashboard, and shipping
   audit/JSON logs to durable storage.
2. **Error tracking** (Sentry or equivalent) for backend exceptions and
   frontend errors; today they land in logs only.
3. **Deploy maturity.** CI pushes SHA-tagged images but there is no
   promotion, canary/blue-green, or documented rollback; ECS deploy is a
   manual doc (`aws_ecs_deployment.md`), not IaC — write the Terraform it
   describes.
4. **Backups/DR.** No snapshot policy for EFS (rag_store, caches), the
   users file, or Redis; define RPO/RTO (data criticality notes are in
   `docs/RUNBOOK.md`).
5. **HA posture.** Single Redis in compose; ElastiCache multi-AZ in prod,
   plus autoscaling policies keyed to the latency metrics.
6. **[done] Runbooks.** `docs/RUNBOOK.md`: restart/reload, KB rebuild,
   model refresh, and per-alert triage.

## 5. Product & data

1. **[gate] Real EHR integration.** Clinical mode correctly refuses the
   synthetic dataset, which means clinical mode has *no* EHR until a FHIR
   (SMART-on-FHIR) connector replaces the demo mockups.
2. **[gate] Clinical validation + regulatory posture.** Advisory framing is
   enforced in code, but a decision-support tool touching diagnosis needs a
   documented clinical evaluation and a CDS-vs-SaMD regulatory assessment
   before real use.
3. **Model governance.** The imaging head (val macro AUROC 0.78) has no
   versioning, eval-set regression check, drift monitoring, or retraining
   pipeline; LLM prompt/model changes are likewise unversioned beyond git.
4. **KB governance.** Corpus is one COVID-era dialogue set + the synthetic
   EHR; provenance, refresh cadence, and clinical review of retrieved
   content are undefined.
5. **Accessibility & i18n.** No WCAG audit (contrast, keyboard nav, screen
   readers on the live HUD); English-only STT and UI.
6. **LICENSE file is missing** while the README claims MIT — the owners
   should add the actual license text (a legal choice, deliberately not
   made by this remediation).

## Suggested sequencing

The session-completable subset is done (R1–R8: JSON salvage, Jinja2,
JSON store, decomposition round 2, typed contracts + /v1, coverage +
supply chain + retrieval eval + load baseline, Playwright smoke, runbook +
alert rules + strict mode). What remains requires external parties or
infrastructure: deploy the alerting stack, extend E2E to the fake-mic
voice flow, FHIR connector, BAAs/de-id, IdP, Trivy/SBOM, Terraform, pen
test, clinical validation — gates first, then the enterprise-hardening
train, with the rest folded into normal feature work (each touched file
leaves smaller than it was found).
