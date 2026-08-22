# Architecture

Module map after the modularization pass. The previous shape — one
1,951-line `api/server.py` and one 1,151-line `ClinicalInterface.tsx` —
is gone; every module below has one job.

## Backend

```
api/
  server.py         55 lines - assembly only: logging, env, clinical-config
                    validation, app creation, middleware install, routers.
                    Stable entry point: `uvicorn api.server:app`.
  settings.py       environment-derived tunables (thresholds, caps, paths)
  state.py          process state: imaging model, retriever handle, EHR
                    records + indices (mutated IN PLACE so cross-module
                    imports stay valid), CheXpert->ontology aliases,
                    live-case store
  guards.py         demo-only refusal, synthetic-EHR ban, LLM-config 503s
  schemas.py        pydantic request bodies
  pipeline.py       the shared inference pipeline: text findings, fusion +
                    evidence recompute, HUD assembly, gated coach questions,
                    final-report prompt
  middleware.py     the HTTP perimeter: request IDs, upload caps, rate
                    limiting, clinical auth gate, audit + metrics, CORS
  routes/
    system.py       /health /metrics /reload_* /knowledge_base
    auth.py         /auth/login /auth/ws-ticket
    inference.py    /infer /image_infer /quick_analysis /multimodal_infer
                    /structured_diagnosis /test_structured_diagnosis
                    /infer_from_image_only
    voice.py        /voice_transcribe /voice_infer /multimodal_voice_infer
    ehr.py          /ehr/* (listing + demo-only mockups)
    cases.py        /api/case* lifecycle, finalize, WS /ws/case/{id},
                    WS /ws/transcribe

core/               domain logic, no FastAPI imports:
  extract, fusion, evidence_engine, retriever, answer, clinical_diagnosis,
  questioner_llm, summarize, diagnostic_suggestions, domains, imaging,
  modeling_biomedclip, voice_transcription, live_stt, llm_client (Claude +
  Gemini + routing), app_mode, auth, audit, metrics, case_store, config,
  logging_setup, ehr_integration, utils

rag_runtime/        offline KB builders + shared chunking
```

Dependency direction (acyclic): `settings <- state <- pipeline <- routes`;
`guards`/`schemas` leaf-shared; `core` never imports `api`.

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
- **Lint gate:** `ruff check .` (correctness classes: E9/F) runs in CI
  before tests.

## Frontend

```
src/
  lib/
    reportMapper.ts   backend response -> ClinicalReport (pure, unit-tested)
    wsClient.ts       live-case WS + HUD normalization (unit-tested)
    pcmTranscriber.ts AudioWorklet -> 16 kHz PCM -> /ws/transcribe
    transcriber.ts    browser Web Speech fallback
  services/api.ts     axios instance, auth token storage, endpoint wrappers
  components/
    ClinicalInterface.tsx  container: state + view switching (876 lines,
                           down from 1,151; further extraction candidates
                           are listed in docs/PRODUCTION_READINESS.md)
    AppHeader.tsx          title, mode chip, demo-only toggles
    LoginModal.tsx         clinical-mode sign-in
    PatientForm, VoiceRecorder, ConversationChat, DifferentialDiagnosis,
    RedFlagAlerts, XAIExplanation, ClinicalReportView, LiveCoach, ...
```

## Verification

Behavior-preserving refactor: 47/47 backend tests and 9/9 frontend tests
pass unchanged (the clinical-auth module dropped its reload machinery -
enabled by the dynamic-config change, not required by it).
