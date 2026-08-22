# Final Re-Audit

Closing step of the approved roadmap (`docs/MASTER_PLAN.md`): the original
defect register re-walked item by item against the finished tree, the
adversarial review findings and their fixes, and the final verification
evidence.

- **Tree state:** branch `claude/medisense-repo-setup-560vwg`, base `490478f`
- **Gates at close:** 47/47 backend tests, 4/4 frontend tests,
  `tsc --noEmit` clean, `CI=true npm run build` clean

## Part II defect register — status

### Blocking

| # | Defect | Status |
|---|---|---|
| 1 | Frontend did not compile (ConversationChat.tsx syntax error + missing ConversationChatRef) | **Closed** (P0) — forwardRef restored; tsc/build/CI gates now enforce it |
| 2 | Fresh clone retrieves nothing (rag_store absent, once-per-process init) | **Closed** (P0/P1/P9/P11) — `make kb`, Docker entrypoint first-boot build, `/reload_retriever` |
| 3 | Composed backend hollow (no keys, no checkpoint, no corpus) | **Closed** (P11) — compose env_file, dockerignore ships checkpoint + corpus |
| 4 | CORS blocked the dockerized frontend | **Closed** (P11) — nginx single-origin proxy; empty REACT_APP_API_URL = same-origin |
| 5 | ECS ALB routing would 404 most routes | **Closed** (P11) — corrected topology: ALB fronts nginx, nginx proxies internally |

### Security & safety

| # | Defect | Status |
|---|---|---|
| 6 | No authentication/authorization | **Closed** (P8) — JWT in clinical mode, roles, WS token auth; demo open by design |
| 7 | No audit trail | **Closed** (P8/P12) — JSONL audit (user/endpoint/patient-id/status/duration); body-borne patient ids documented as a gap |
| 8 | Unsafe torch.load; mktemp race | **Closed** (P6) — weights_only=True; mkstemp |
| 9 | Fabricated 0.99 imaging fallback | **Closed** (P6) — score 0.60, `fallback: true`, explanatory note |
| 10 | No rate limiting/upload caps; stale env template | **Closed** (P8/P0) — sliding-window limiter (XFF-aware), Content-Length cap + 411 for length-less chunked posts, rewritten .env.example |

### Correctness & honesty

| # | Defect | Status |
|---|---|---|
| 11 | Mocked features presented as real | **Closed** (P7) — demo-mode-only with 403 refusal in clinical; XAI panel now renders real evidence (P6); Download/Print/Share remain demo-inert (accepted: cosmetic, demo-only surface) |
| 12 | /voice_infer missing evidence; questions hard-disabled | **Closed** (P6) — evidence engine added; gated questions re-enabled |
| 13 | Frontend dead/broken calls (quick_entry, dropped patient, wav mislabel, unused explainability payload) | **Closed** (P6) — removed/fixed/wired |
| 14 | Config drift (orphaned extract.j2, dead rag.yaml keys, slug mismatches, pseudo-Jinja) | **Closed** (P1/P6) — vocabulary reconciled (102 labels, zero producers outside it); dead config removed. The `.j2` str.replace rendering remains (accepted: documented behavior, no template injection surface) |
| 15 | Docs referencing missing files; contradictory cloud plans | **Closed** (P6/P11) — EKS plan deleted; ECS doc corrected; readmes point at real files |

### Scalability

| # | Defect | Status |
|---|---|---|
| 16 | All state in-process | **Closed** (P9) — Redis-backed case store (TTL) with capped memory fallback; per-message persistence in the WS loop |
| 17 | WS pipeline blocked the event loop | **Closed** (P3) — asyncio.to_thread + burst collapse; STT has a dedicated executor (P5) |
| 18 | No tests; CI ran none | **Closed** (P10) — 45 backend + 4 frontend tests gate the image build; PR trigger restored |
| 19 | Startup coupled to network + image hashing | **Closed** (P9) — SKIP_HASH defaults on; model caches volume-mounted; warm-up off the request path (P2). HF backbone download at first imaging load remains (accepted: cache volume/EFS mitigates) |

## Adversarial review round

A high-effort review of the full diff produced 15 verified findings; all 15
were fixed in the P13 round and covered with regression tests where testable:

1. Compose first-boot KB build failed on the bind mount (rmtree EBUSY) — build without `--reset`.
2. Clinical-mode live case/finalize fetches lacked the bearer token — authHeaders on all raw fetches.
3. Synthetic-EHR ban didn't cover inference endpoints — `_ehr_for_patient` + image-resolution guard + regression test.
4. STT socket unavailable → silent no-transcription — readiness handshake; client falls back to browser STT.
5. Claude-path questions could never raise the red-flag alert — [red-flag] tagging + parsing + ordering.
6. WS burst drain could lose the final utterance on disconnect — per-message ingest + persist.
7. Live teardown raced the STT flush transcript — deferred onStopLive (3.5 s, cancelled on restart).
8. Prescriptive filter false-positives gutted streamed questions — pattern-based filter (dosing/prescribing), regression-tested both directions.
9. Rate limiter keyed on the proxy IP — first X-Forwarded-For hop honored.
10. Burst collapse dropped intermediate transcript echoes — every drained utterance echoed; frontend merges HUD partials.
11. Stale-closure duplicate chat lines — live detection via wsRef.
12. Audit missed path-borne patient ids — extracted from /ehr/patients/{id}; body-borne ids documented.
13. Metrics label cardinality/escaping — route-template labels + label escaping + rate-bucket pruning.
14. Chunked-transfer bypass of the upload cap — 411 for length-less chunked POSTs.
15. Dialogue chunker dropped short tails — merged into the previous chunk, regression-tested.

## Security review round

An independent security-focused pass over the complete diff (auth middleware,
JWT issuance/validation, mode gating, deserialization surfaces, temp-file
handling, Redis serialization, nginx/Docker/CI changes) cleared every area
examined - notably: the `demo-secret` signing fallback is unreachable in
clinical mode (boot refuses without AUTH_SECRET_KEY), algorithms are pinned
(no confusion), the PUBLIC_PATHS prefixes shadow no sensitive routes, and the
case store is pure JSON (no pickle). One finding met the bar:

- **WS bearer token in the URL (CWE-598, medium):** clinical-mode WebSockets
  authenticated with the 8-hour session JWT as a `?token=` query parameter,
  and the same change set's nginx proxy logs full request lines - persisting
  live clinician credentials into access-log infrastructure. **Fixed:**
  `POST /auth/ws-ticket` mints a ~60 s WS-scoped ticket that the browser
  clients now put in socket URLs instead of the session JWT; REST rejects
  ticket-scoped tokens outright, so a logged ticket is useless beyond its
  expiry and scope; nginx additionally disables access logging for `/ws/`
  paths. Regression-tested (ticket authenticates a socket, is refused by
  REST, and minting requires a session).

## Environment limitations (honest bounds of this verification)

- LLM round-trips (Gemini/Claude) were not exercised against live APIs — no
  keys in the build environment. Both paths are covered by mocks, degraded-
  mode contract tests, and the routing matrix; first run with real keys
  should smoke `/infer`, the WS coach stream, and `/api/case/{id}/finalize`.
- Docker image builds were validated at YAML/syntax level plus per-step
  in-session verification; no docker daemon was available to run
  `docker compose up`.
- Imaging inference not exercised (no open_clip/HF backbone install);
  degraded imaging contract is test-covered.
- Real-microphone STT not exercised; VAD/WAV/socket layers are test-covered
  and tiny.en transcribed synthetic audio.
