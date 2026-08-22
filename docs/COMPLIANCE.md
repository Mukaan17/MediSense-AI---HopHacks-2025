# Compliance Posture

Scope: what the platform does with clinical data today, what protections are
in place, and what must be true **before any real patient data (PHI) enters
the system**. Companion to `docs/MASTER_PLAN.md`.

## Modes and data classes

| Mode | Data | Auth | Mocked integrations |
|---|---|---|---|
| `demo` (default) | Synthetic only: MIMIC-IV Clinical Demo v2.2 records paired with **unrelated** CheXpert images (`ehr_synthetic: true` in `/health`) | None | Enabled, labeled |
| `clinical` | Operator-configured (`EHR_JSON`) | JWT required on every endpoint and WebSocket | Refused (403) |

The bundled dataset is de-identified source material (PhysioNet demo +
CheXpert) with a synthetic patient-image pairing; it contains no PHI. The
demo-mode UI banner states this.

## PHI data flow (clinical mode)

```
clinician browser ──TLS──> nginx ──> FastAPI backend
    │ audio (mic PCM)            │ conversation text, EHR record
    │                            ├─> deterministic extraction (in-process)
    │                            ├─> FAISS retrieval (in-process, local store)
    │                            ├─> imaging model (in-process)
    │                            ├─> faster-whisper STT (in-process)
    │                            └─> LLM APIs (conversation-derived text +
    │                                 EHR summary + candidate conditions)
    └────────────────────────────────► Anthropic / Google endpoints
```

Only the LLM calls leave the deployment boundary. They carry
conversation-derived text, the EHR summary, and retrieved reference chunks.

## Requirements before real PHI

1. **Vendor agreements**: enterprise terms with a BAA (or equivalent) for
   Anthropic and Google AI *before* any PHI reaches `generateContent` /
   the Messages API. Without them, clinical deployments must run with LLM
   features disabled or behind a de-identification layer.
2. **Transport encryption**: TLS at the ALB; internal traffic inside a
   private VPC. No plain-HTTP exposure of the backend.
3. **At-rest encryption**: EFS (rag_store, caches), ElastiCache, and any
   log destinations encrypted with KMS.
4. **Access control**: `APP_MODE=clinical`, `AUTH_SECRET_KEY` from Secrets
   Manager, per-user accounts via the users registry, role separation
   (clinician/admin). No shared credentials.
5. **Audit**: `logs/audit.log` (JSONL: user, endpoint, patient identifier,
   status, duration - never clinical content) shipped to durable storage
   with retention per organizational policy. The audit trail is the record
   of who accessed which patient's data and when.
6. **Retention**: live cases expire via `CASE_TTL_SECONDS` (default 1 h)
   and are never persisted beyond Redis TTL; no conversation content is
   written to disk by the application. Define retention for anything the
   operator adds (EHR source, log shipping).
7. **Advisory framing**: outputs are constrained to a closed condition
   vocabulary, prescriptive language is filtered from generated questions,
   fallback imaging predictions are labeled as placeholders, and every
   report carries an advisory-only disclaimer. The system is decision
   *support*; it must not be represented as a diagnostic device (which
   would trigger medical-device regulatory pathways).

## Known gaps (tracked, not yet closed)

- No de-identification layer in front of the LLM calls; PHI minimization
  currently relies on prompt construction (summaries, not raw records).
- Users registry is file-based; enterprise deployments should front an IdP
  (OIDC) instead.
- Audit log shipping/immutability is deployment-specific and not automated
  by this repository.
- The audit middleware attributes patient identifiers from query and path
  parameters; a patient_id inside a JSON/form body (e.g. POST /infer) is
  not parsed at the middleware layer.
