# Production Readiness — What's Left

Rigorous gap analysis after the remediation roadmap (`docs/MASTER_PLAN.md`,
`docs/REAUDIT.md`) and the modularization pass (`docs/ARCHITECTURE.md`).
Everything here is *open* work, ranked within each category. Items marked
**[gate]** should block a real clinical go-live; the rest are hardening and
maturity.

## 1. Code & architecture

1. **Typed response contracts.** Endpoints return ad-hoc dicts; define
   pydantic response models per route so the OpenAPI schema is a real
   contract and the frontend can generate a typed client (openapi-ts)
   instead of hand-written axios wrappers with `any`.
2. **Further decomposition candidates** (the split so far took the two god
   modules apart; these are the next-largest):
   - `api/routes/cases.py` (428): REST lifecycle vs. the two WebSocket
     handlers could separate (`cases.py` / `ws.py`).
   - `core/clinical_diagnosis.py` (580): structured differential vs. risk
     rules vs. brief summary are three modules living in one file.
   - `ClinicalInterface.tsx` (876): extract a `useLiveCase` hook (case
     creation, WS lifecycle, pending-utterance queue), `LiveAnalysisPanel`,
     and `InputView`/`ResultsView` screens.
3. **Dependency injection.** State lives in module-global singletons
   (`api/state.py`). Honest at this scale, but an app-factory pattern with
   injected state would allow parallel test isolation and multi-tenant
   configuration.
4. **Consolidate LLM JSON salvage.** The fence-strip/brace-scan parser is
   copy-pasted in `answer.py`, `clinical_diagnosis.py`, `questioner_llm.py`,
   `extract.py`; `core/utils.json_sanitize` exists for this. One robust
   parser, unit-tested against malformed outputs.
5. **Template honesty.** `config/prompts/*.j2` are rendered by
   `str.replace`. Adopt real Jinja2 (with autoescape off and strict
   undefined so typos fail loudly) or rename to `.txt`.
6. **API versioning.** No `/v1` prefix; any breaking response change breaks
   clients silently. Version now while there is one consumer.
7. **frontend `tsconfig` strict mode** is off; `any` casts hide contract
   drift. Turn on incrementally (`strict: true`, fix per-directory).

## 2. Testing

1. **[gate] End-to-end browser tests.** No Playwright coverage; the live
   voice flow (mic -> worklet -> WS -> HUD) and clinical login flow are
   only manually verifiable. Playwright with a fake media stream
   (`--use-fake-device-for-media-stream` + a WAV fixture) can cover both.
2. **LLM contract tests.** Claude/Gemini calls are mocked or degraded in
   CI; record-and-replay fixtures (VCR-style) for one golden conversation
   per path would catch prompt/parse regressions without live keys.
3. **Coverage measurement** (pytest-cov + jest --coverage) with a ratchet,
   so the suite's blind spots are visible in review.
4. **Automated load baseline.** `scripts/ws_load_test.py` exists but is not
   run anywhere; a nightly job against a composed stack with latency
   budgets (e.g. p95 per-utterance HUD < 3 s CPU-only, LLM mocked) would
   catch pipeline regressions.
5. **Retrieval quality evals.** No metric guards the KB: a small labeled
   query set with recall@k / rerank-gain assertions would catch embedding
   or chunking regressions.

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
4. **Supply chain.** No Dependabot/pip-audit/npm-audit in CI, no image
   scanning (Trivy), no SBOM. The pinned-but-aging Python set (fastapi
   0.116, sentence-transformers 2.7) needs a scheduled update lane.
5. **Pickle in the RAG store.** `texts.pkl`/`metas.pkl` are trusted local
   files, but JSON/parquet would remove the deserialization class entirely.
6. **In-cluster TLS.** nginx -> backend is plaintext inside the network
   boundary; mTLS or a mesh if the hospital's zoning requires it.
7. **Pen test** before clinical go-live; the internal reviews are strong
   but not independent.

## 4. Operations

1. **[gate] Alerting.** `/metrics` exists but nothing watches it: define
   alerts (error-rate, p95 latency per stage, LLM failure rate, token
   spend/day) and a dashboard; ship audit + JSON logs to durable storage.
2. **Error tracking** (Sentry or equivalent) for backend exceptions and
   frontend errors; today they land in logs only.
3. **Deploy maturity.** CI pushes SHA-tagged images but there is no
   promotion, canary/blue-green, or documented rollback; ECS deploy is a
   manual doc (`aws_ecs_deployment.md`), not IaC — write the Terraform it
   describes.
4. **Backups/DR.** No snapshot policy for EFS (rag_store, caches), the
   users file, or Redis; define RPO/RTO.
5. **HA posture.** Single Redis in compose; ElastiCache multi-AZ in prod,
   plus autoscaling policies keyed to the latency metrics.
6. **Runbooks.** Restart/reload procedures, KB rebuild, model refresh, and
   on-call triage notes exist only as scattered README sections.

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

Gates first: alerting, E2E tests, FHIR connector, BAAs/de-id, clinical
validation. Then IdP + supply chain + IaC as one "enterprise hardening"
train, with the remaining code-quality items folded into normal feature
work (each touched file leaves smaller than it was found).
