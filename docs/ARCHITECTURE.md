# Architecture

Module map after the modularization pass (R4) and the improvement round
(I0–I17). The previous shape — one 1,951-line `api/server.py` and one
1,151-line `ClinicalInterface.tsx` — is gone; every module below has one
job.

## Backend

```
api/
  server.py         87 lines - assembly only: logging, env, secret
                    hydration, Sentry init, clinical-config validation,
                    app creation (lifespan warm-up), store-outage 503
                    handler, middleware install, dual-mounted routers.
                    Stable entry point: `uvicorn api.server:app`.
  settings.py       environment-derived tunables (thresholds, caps, paths)
  state.py          process state: imaging model, retriever handle, EHR
                    records + indices (mutated IN PLACE so cross-module
                    imports stay valid), CheXpert->ontology aliases,
                    live-case store + durable-store event helpers
  guards.py         demo-only refusal, synthetic-EHR ban, LLM-config 503s
  schemas.py        pydantic request bodies
  responses.py      typed response models (the OpenAPI contract source)
  pipeline.py       the shared inference pipeline: text findings, fusion +
                    evidence recompute, HUD assembly, gated coach
                    questions, final-report generation
  middleware.py     the HTTP perimeter: request IDs, upload caps, rate
                    limiting, clinical auth gate (cookie/Bearer + CSRF),
                    audit + metrics, CORS
  routes/
    system.py       /health /metrics /reload_* /knowledge_base
    auth.py         /auth/login /auth/logout /auth/me /auth/ws-ticket
                    /auth/oidc/login /auth/oidc/callback
    inference.py    /infer /image_infer /quick_analysis /multimodal_infer
                    /structured_diagnosis /test_structured_diagnosis
                    /infer_from_image_only
    voice.py        /voice_transcribe /voice_infer /multimodal_voice_infer
    ehr.py          /ehr/* (listing + demo-only mockups)
    cases.py        /api/case* REST lifecycle, finalize (inline or
                    queued), report polling, question feedback
    history.py      /api/cases + /api/case/{id}/timeline (503 without a
                    durable store)
    ws.py           WS /ws/case/{id} (live HUD), WS /ws/transcribe (STT)

core/               domain logic, no FastAPI imports:
  extract, fusion, evidence_engine, retriever, answer, questioner_llm,
  summarize, diagnostic_suggestions, domains, imaging, calibration,
  modeling_biomedclip, voice_transcription, live_stt (sized worker pool),
  llm_client (Claude + Gemini + routing + structured JSON modes),
  app_mode, auth (JWT + cookie sessions + CSRF), oidc, secrets, audit,
  metrics (prometheus_client), tracing (no-op OTel spans),
  error_tracking (Sentry, DSN-gated), case_store (memory/Redis, layered
  with the durable store), config, logging_setup, ehr_integration, utils
  diagnosis/        structured differential (differential.py),
                    deterministic risk/red-flag rules (risk.py), brief
                    summary (summary.py); core/clinical_diagnosis.py
                    remains as a compat shim
  persistence/      SQLAlchemy durable store (CASE_DB_URL): case
                    snapshots, append-only case_events, reports;
                    migrations in migrations/ (alembic)
  fhir/             SMART-on-FHIR R4 connector (backend-services JWT,
                    LOINC vitals mapping, DocumentReference write-back);
                    active when EHR_SOURCE=fhir

worker/             arq worker (same image): finalize-report jobs when
                    FINALIZE_MODE=queue, retention cron
                    (CASE_RETENTION_DAYS)
rag_runtime/        offline KB builders + shared chunking
infra/terraform/    the ECS deployment as code (see its README)
```

Dependency direction (acyclic): `settings <- state <- pipeline <- routes`;
`guards`/`schemas` leaf-shared; `core` never imports `api`; `worker`
imports both but nothing imports `worker`.

Conventions that keep it that way:

- **State identity is stable.** `api/state.py` containers are mutated in
  place (`_load_ehr` clears + extends); singleton resets go through
  functions (`reset_retriever_singleton`). Rebinding a state global breaks
  every from-import - don't.
- **Mode and auth config are read per call** (`core/app_mode`,
  `core/auth`): tests flip `APP_MODE` with plain env vars, no module
  reloads. Clinical boot validation runs once in `api/server.py`.
- **Routes stay thin.** Multi-step logic belongs in `api/pipeline.py` or
  `core/`; a route composes and serializes.
- **Lint gate:** `ruff check .` runs in CI before tests.
- **Contract gate:** `openapi.json` at the repo root is the committed API
  contract (`python scripts/export_openapi.py`); CI fails on drift, the
  frontend's TypeScript types are generated from it
  (`npm run gen:api` -> `src/api/schema.d.ts`, also freshness-checked),
  and a schemathesis job fuzzes every operation for undocumented server
  errors. CI is path-filtered: frontend-only changes skip backend jobs
  and vice versa, and the two images build and push independently after
  a blocking dependency audit, a Trivy scan, SBOM generation, and
  (when a key is configured) cosign signing.

## Frontend

Toolchain: Vite + vitest (TypeScript 5, `strict` + `noUnusedLocals`);
`npm run build` outputs to `build/`. API types are generated from the
committed OpenAPI contract (`npm run gen:api`). Runtime configuration
comes from `config.js` (`window.__MEDISENSE_CONFIG__`), templated at
container start - one build runs against any backend. Clinical auth is
an httpOnly session cookie + double-submit CSRF header; no tokens in
localStorage.

```
src/
  api/schema.d.ts     generated API types (freshness-gated in CI)
  lib/
    reportMapper.ts   backend response -> ClinicalReport (pure, unit-tested)
    wsClient.ts       live-case WS + HUD normalization (unit-tested)
    pcmTranscriber.ts AudioWorklet -> 16 kHz PCM -> /ws/transcribe
    transcriber.ts    browser Web Speech fallback
  services/api.ts     axios instance, CSRF interceptor, endpoint wrappers
  hooks/
    useLiveCase.ts    live-case lifecycle: case creation, WS connect,
                      pending-utterance queue, HUD/confidence history,
                      question feedback, finalize + report polling
  components/
    ClinicalInterface.tsx  container: state + view switching
    AppHeader.tsx          title, mode chip, demo-only toggles
    LoginModal.tsx         clinical-mode sign-in (password or OIDC)
    LiveAnalysisPanel.tsx  live HUD: differential, confidence sparkline,
                           feedback buttons, final report, print/PDF
    CaseHistory.tsx        persisted-case list + timeline view
    KnowledgeBaseToggle.tsx KB status panel (real store facts)
    PatientForm, VoiceRecorder, ConversationChat, DifferentialDiagnosis,
    RedFlagAlerts, XAIExplanation, ClinicalReportView, LiveCoach, ...
```

## Verification

The standing gate suite: 147 backend tests + ruff, `tsc --noEmit`,
9 vitest unit tests, production build, Playwright demo (5 specs,
including the fake-mic voice flow and an axe-core scan) and clinical
(login gate) suites, OpenAPI/type freshness, schemathesis contract fuzz.
