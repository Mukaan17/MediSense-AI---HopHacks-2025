# MediSense Master Plan

Audit of the 5-improvement competition plan against the codebase, the consolidated
platform defect register, and the approved integrated roadmap: corrected improvements
first, then clinical-grade production hardening with a demo-mode switch, closing with
a final re-audit.

- **Baseline commit:** `490478f` (merge of PR #1, `full-application`)
- **Working branch:** `claude/medisense-repo-setup-560vwg`
- **Posture:** clinical-grade with an `APP_MODE=demo|clinical` switch
- **Runtime:** laptop CPU for dev/testing, AWS ECS at hospital-network scale
- **LLM strategy:** Claude primary (live: Haiku 4.5, final report: Sonnet), Gemini fallback

---

## Part I — Competition plan audit

Every file path, line number, and dependency claim in the 5-improvement plan was
verified against the repository. The plan's codebase knowledge is accurate — all cited
line ranges are correct, `CrossEncoder` ships in the pinned
`sentence-transformers==2.7.0`, and the phase ordering (5 → 3 → 2 → 4 → 1) is sensible.
The defects are in the new code it proposes.

| Phase | Verdict | Summary |
|---|---|---|
| 1 · RAG chunking + metadata | Sound, minor fixes | Line refs exact; chunk size and citation labeling need adjustment; metadata extracted but never used. |
| 2 · Cross-encoder re-rank | Sound, minor fixes | Correct API and dependency; the async concern is real but far bigger than the plan admits. |
| 3 · Claude streaming + final report | Needs corrections | Fake streaming, a crash bug in finalize, a dropped safety filter, stale model IDs / SDK pin. |
| 4 · Model routing config | Sound, minor fixes | One wrong fallback model; Ollama section is dead config unless implemented. |
| 5 · faster-whisper live STT | Redesign required | Audio format assumption wrong end-to-end (WebM/Opus fragments vs. raw PCM); needs AudioWorklet capture + VAD endpointing. |

### Phase 1 — RAG chunking + metadata

- **Verified:** `_flatten` ends at line 40, `_read_json_docs` spans 43–62 (inline
  metadata dict at line 56), collect loop at 83–98. "English Train.json" items carry
  `description` + `utterances`, so the proposed `source_type` detection works.
- **Chunk size:** 250-word windows are ~330+ tokens — past all-MiniLM-L6-v2's
  256-token effective window. Use ~180-word windows and split dialogue items on
  utterance boundaries rather than mid-turn.
- **Unused metadata:** `source_type`/`condition_label`/`age`/`sex` are indexed but
  nothing retrieves by them. Decision: metadata is citation/display-only for now
  (documented), available for future filtering.
- **Citations:** `render_docs` labels hits `§item_N`; after chunking, fold `chunk_idx`
  into the section label (`item_N.c2`) so citations stay unambiguous.
- **Verification gap:** the retriever init is once-per-process (`_init_attempted`),
  so the server must restart (or reload) after a KB rebuild.

### Phase 2 — Cross-encoder re-ranking

- **Verified:** `get_relevant_documents` is exactly lines 39–58; `_cfg` in scope;
  `CrossEncoder` imports from the pinned sentence-transformers.
- **Async understated:** the plan wraps only the CE call in an executor. The actual
  retrieval call is `server.py:1420` inside `_send_update` — an async function whose
  entire body (extraction, FAISS, fusion, the LLM call) blocks the event loop on every
  WebSocket utterance. Fix once, properly, in P3: run the whole per-utterance pipeline
  via `asyncio.to_thread`.
- **Cold start:** first CE use downloads `ms-marco-MiniLM-L-6-v2` — pre-warm at startup.

### Phase 3 — Claude streaming + deep final report

- **Fake streaming (critical):** the proposed `stream_claude_tokens` runs the sync SDK
  stream in `run_in_executor`, collects all tokens, then yields them after completion —
  token-by-token delivery never happens. Correct: `AsyncAnthropic` +
  `async with client.messages.stream(...)` + `async for text in stream.text_stream`.
- **Crash bug (critical):** `/api/case/{id}/finalize` iterates `u['speaker']`/`u['text']`,
  but `case["utterances"]` is a list of prefixed strings (`"patient: chest pain"`,
  server.py:1506–1507). Fix: `"\n".join(utterances)`.
- **Safety filter dropped (critical):** the existing `propose_questions_llm`
  keyword-blocks prescriptive wording (take/start/mg/dose/prescribe/diagnose). The new
  `_parse_bullet_questions` path has no such filter. Carry it over.
- **Stale identifiers:** use `claude-haiku-4-5` (current model IDs take no date
  suffix). `claude-sonnet-4-6` is valid for the final report. Pin `anthropic>=1.0`.
  Replace `asyncio.get_event_loop()` with `asyncio.to_thread`/`get_running_loop()`.
- **Hidden dependency:** the frontend halves cannot compile until the pre-existing
  `ConversationChat.tsx:61` syntax error is fixed — P0 is a hard prerequisite.

### Phase 4 — Model routing config

- **Wrong fallback:** `fallback_final: "gemini-2.0-flash"` downgrades a generation for
  the deep report. Use `gemini-2.5-flash`.
- **Dead config risk:** the `ollama:` block ships with no client implementation.
  Decision: cut it (documented as future work).
- **Adjacent existing bug:** `get_llm()` caches by model name only — a changed
  temperature is silently ignored once cached. Fix while touching the file.

### Phase 5 — faster-whisper live chunked transcription

- **Format mismatch (critical):** MediaRecorder with `timeslice=2000` emits WebM/Opus
  container fragments — only the first blob has headers, none of it is raw 16 kHz PCM.
  The proposed backend wraps the bytes in a hand-built WAV header assuming raw mono
  16-bit PCM. Redesign: an AudioWorklet on the mic stream, downsampling
  Float32 → 16 kHz Int16 PCM client-side, sending raw PCM frames — which then matches
  the proposed backend exactly (whose WAV header struct is itself correct).
- **No utterance segmentation:** fixed 2-second chunks cut words mid-syllable. Use
  VAD-driven endpointing — emit transcripts on silence, not on a timer.
- **Not wired to the live case:** final transcripts must feed both Clinical Notes and
  `sendUtterance` → `/ws/case/{id}`. Also fix the existing arity bug in
  `VoiceRecorder.tsx` (two callbacks passed to a one-parameter transcriber).
- **Resource duplication:** faster-whisper `tiny.en` alongside WhisperX `base`; give
  chunk transcription a dedicated executor; keep WhisperX only for diarized uploads.

**Where the plan fits:** it is a feature-quality track, not a production track. It runs
first (per owner direction) with a small P0 in front, because plan Phases 3 and 5
cannot be compiled or verified until the frontend build is fixed and a KB exists.

---

## Part II — Platform defect register

### Blocking (breaks build, deploy, or a demo)

1. Frontend does not compile — stray `});` at `ConversationChat.tsx:61` plus imports of
   a nonexistent `ConversationChatRef` used at 5 call sites in `ClinicalInterface.tsx`.
   Breaks `npm run build`, `Dockerfile.frontend`, compose, and the CI frontend image.
2. Fresh clone retrieves nothing — `rag_store/` is gitignored and absent; retriever
   init is once-per-process; `/health` reports `doc_count: 0` silently.
3. Composed backend is hollow — compose passes no `GEMINI_API_KEY`; `.dockerignore`
   excludes the checkpoint, corpus, and `.env`.
4. CORS blocks the dockerized frontend — nginx `:80` absent from default
   `FRONTEND_ORIGINS`; API base baked to `localhost:8000` with no build arg.
5. ECS plan routes wrong — the documented ALB rule (`/api/*` → backend) matches only
   the live-case routes; `/health`, `/infer`, `/ehr/*`, `/ws/*` would 404.

### Security & safety (clinical-grade must-fix)

6. Zero authentication/authorization anywhere, with `allow_credentials=True` CORS
   (`python-jose`/`passlib` pinned but imported nowhere).
7. No audit trail of inference or EHR access; unstructured print logging.
8. `torch.load` without `weights_only=True`; `tempfile.mktemp` race in voice
   preprocessing.
9. Imaging fallback fabricates a prediction at hardcoded 0.99 confidence from the
   EHR-linked label, presented like a model output.
10. No rate limiting or upload validation; stale Groq-flavored `.env.example`.

### Correctness & honesty of features

11. Mocked-but-presented-as-real: EHR import/export (hardcoded "Epic"), knowledge-base
    toggle, XAI panel (fixed hypertension demo content), report Download/Print/Share,
    client-side-mocked FHIR import.
12. `/voice_infer` skips the evidence engine; question generation hard-disabled in
    `/structured_diagnosis` and `/multimodal_infer`.
13. Frontend: `futureAPI.quickEntry` targets nonexistent `/quick_entry`; text-only
    Quick Analysis drops the patient object; audio Blob mislabeled `audio/wav`;
    posterior-shift explainability payload typed but never rendered.
14. Config drift: orphaned `extract.j2`; unimplemented `rag.yaml` keys; label-slug
    mismatches across `labels.json`/`symptom_map.json`/`mappings.yaml`; ".j2" files
    rendered by `str.replace`, not Jinja2.
15. Docs reference missing files; two contradictory cloud plans; embedding-model name
    contradiction across docs.

### Scalability (the hospital-network gap)

16. All state in-process (`_CASES` unbounded dict, EHR indices, model singletons) —
    lost on restart, broken under >1 worker, unshareable across ECS tasks.
17. WS handler runs the full pipeline (including a synchronous LLM call) on the event
    loop per utterance.
18. No tests; CI runs none (build-only, and only on pushes to a dead branch).
19. Startup coupled to the network (HF hub download) and to sha256-hashing every EHR
    image.

---

## Part III — Integrated roadmap (approved)

Sequencing per owner direction: improvements → production hardening → final re-audit,
with a minimal P0 in front. Every phase lands with its own verification; P6+ land with
tests. One commit per phase on `claude/medisense-repo-setup-560vwg`.

### P0 — Unblock the tree (~2–3 h)

- Fix `ConversationChat.tsx`: real `forwardRef` + `useImperativeHandle` exporting
  `ConversationChatRef` (addTranscriptMessage/resetChat); fix the
  `startBrowserTranscriber` arity bug in `VoiceRecorder.tsx`.
  Gate: `npx tsc --noEmit` and `npm run build` pass.
- Bootstrap the KB: script/make target; document restart-after-build; `/health` shows
  nonzero `doc_count`.
- Rewrite `.env.example` to the variables the code actually reads (Gemini + Anthropic,
  imaging, RAG, thresholds); remove the Groq ghosts.
- Smoke baseline: `smoke_test.py` green locally.

### P1 — Improvement 5: RAG chunking + metadata, corrected (~2–3 h)

- ~180-word token-aware windows with overlap; utterance-boundary splitting for
  dialogue items; `chunk_idx` folded into citation section labels; metadata stored
  (citation-only for now); `rag.yaml` chunking + retrieval config.
- Verify: rebuild logs chunked count ≫ item count; restart; citations show
  chunk-level sections.

### P2 — Improvement 3: cross-encoder re-ranking, corrected (~1.5–2 h)

- FAISS search widened to `candidate_k` (default 20) → lazy CrossEncoder
  (`ms-marco-MiniLM-L-6-v2`) → top_k (5). Pre-warm at startup. Executor question
  deferred to P3's wholesale event-loop fix.
- Verify: A/B a respiratory query with reranker toggled.

### P3 — Improvement 2: Claude streaming + deep final report, corrected (~4–5 h)

- True async streaming via `AsyncAnthropic().messages.stream` (token-by-token);
  models `claude-haiku-4-5` live / `claude-sonnet-4-6` final; pin `anthropic>=1.0`.
- Finalize endpoint joins the real string utterances; final report uses a structured
  prompt with the closed label set + advisory framing.
- Prescriptive-language filter ported onto parsed streamed questions.
- Entire per-utterance WS pipeline moved off the event loop (`asyncio.to_thread`)
  with per-case recompute debounce.
- Frontend: `streaming_token` routing in wsClient + live display.
- Verify: tokens arrive incrementally; finalize works on a multi-turn case; Gemini
  path intact without `ANTHROPIC_API_KEY`.

### P4 — Improvement 4: model routing config, corrected (~1 h)

- `config/models.yaml` + `load_models()` + `get_live_model()/get_final_model()`;
  `fallback_final: gemini-2.5-flash`; Ollama block cut; `get_llm()` cache keyed by
  model + temperature.

### P5 — Improvement 1: server-side live STT, redesigned (~5–6 h)

- AudioWorklet mic capture → Float32 → 16 kHz Int16 PCM → raw frames over
  `/ws/transcribe`; VAD-driven utterance endpointing; transcripts feed both Clinical
  Notes and the live-case WS; Web Speech kept as fallback; faster-whisper `tiny.en`
  with a dedicated executor.
- Verify: cross-browser live transcription drives the HUD.

### P6 — Correctness sweep (~6–8 h)

- Backend: evidence engine into `/voice_infer`; re-enable gated questions in
  `/structured_diagnosis`/`/multimodal_infer` (async-safe post-P3);
  `weights_only=True`; `mktemp` → `NamedTemporaryFile`; imaging fallback labeled as
  such in responses; label slugs reconciled; orphaned config removed or implemented.
- Frontend: XAI panel wired to real posterior-shift data; dead API functions removed;
  audio MIME corrected; full patient object sent on `/infer`.
- Docs: one README matching reality; obsolete EKS plan removed.

### P7 — Demo-mode switch (~4–6 h)

- `APP_MODE=demo|clinical`, surfaced via `/health` and a UI banner.
- Demo: synthetic dataset clearly labeled, mock EHR import/export enabled, every
  feature showcased. Clinical: mocks disabled, auth required, synthetic endpoints
  refuse. One codebase, config-switched.

### P8 — Security & auth (~8–12 h)

- JWT auth (`python-jose`/`passlib`), roles (clinician/admin), WS token auth,
  tightened CORS, rate limiting, upload validation.
- Structured, PHI-conscious audit log of every inference, EHR access, and export.
- Secrets via AWS Secrets Manager in ECS, `.env` locally.

### P9 — State & scale (~8–10 h)

- `_CASES` externalized to Redis (ElastiCache in prod) with TTLs; in-memory fallback
  for dev; retriever reload hook; worker-safe startup; HF backbone cached in
  image/EFS; `SKIP_HASH` default on with async index build.
- WS load test + per-stage latency budgets.

### P10 — Tests & CI gates (~8–10 h)

- pytest: extraction, fusion math, evidence shifts, chunker, retriever fixture,
  question filter, finalize; TestClient suites per route group; WS test.
- Frontend: tsc, build check, unit tests for the API mapper + wsClient routing.
- CI: PR trigger restored; test + lint jobs gate the image build; smoke in CI.

### P11 — Deployment: laptop CPU ⇄ AWS ECS (~6–10 h)

- `Dockerfile.cpu` as the default dev/demo image (no CUDA, no custom_ops); GPU image
  kept for ECS imaging capacity.
- Compose fixed: `env_file`, checkpoint + KB available, `FRONTEND_ORIGINS`,
  `REACT_APP_API_URL` build arg, nginx reverse proxy for single-origin serving.
- ECS corrections: ALB routing covering the real API surface, Secrets Manager, EFS
  for rag_store/HF cache, WS-aware target group settings.

### P12 — Observability & compliance posture (~6–8 h)

- Structured JSON logs with request IDs; per-stage latency and error metrics;
  token/cost accounting per model call.
- Clinical-mode groundwork: PHI data-flow map, vendor enterprise terms/BAAs before
  real PHI reaches an LLM, encryption at rest, retention policy, advisory-only
  framing review.

### P13 — Final re-audit (~3–4 h)

- Defect register re-walked item by item; code + security review over the changed
  tree; smoke/e2e/load regression; updated architecture reference.
- Exit criteria: every Part II item closed or explicitly accepted; demo mode
  showcases all features end-to-end on a laptop; clinical mode deploys green on ECS.

---

## Resolved decisions

- **Ollama:** out (future work; no dead config).
- **RAG metadata:** citation/display-only for now.
- **Diarized batch uploads:** retained on the WhisperX path; faster-whisper serves
  live chunks.
