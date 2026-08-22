# Compliance Posture

Scope: what the platform does with clinical data today, what protections are
in place, and what must be true **before any real patient data (PHI) enters
the system**. Companion to `docs/PRODUCTION_READINESS.md`.

## Modes and data classes

| Mode | Data | Auth | Mocked integrations |
|---|---|---|---|
| `demo` (default) | Synthetic only: MIMIC-IV Clinical Demo v2.2 records paired with **unrelated** CheXpert images (`ehr_synthetic: true` in `/health`) | None | Enabled, labeled |
| `clinical` | Operator-configured: `EHR_JSON` file or a SMART-on-FHIR R4 server (`EHR_SOURCE=fhir`) | Required on every endpoint: httpOnly session cookie + double-submit CSRF, or Bearer JWT; optional OIDC SSO (`AUTH_MODE=oidc`). WebSockets use short-lived tickets, never the session token in URLs | Refused (403) |

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
    │                            ├─> Redis (live case state, TTL-bounded)
    │                            ├─> Postgres (optional durable case store)
    │                            ├─> FHIR server (EHR read; report write-back)
    │                            └─> LLM APIs (conversation-derived text +
    │                                 EHR summary + candidate conditions)
    └────────────────────────────────► Anthropic / Google endpoints
```

Only the LLM calls leave the deployment boundary; they carry
conversation-derived text, the EHR summary, and retrieved reference
chunks. Redis, Postgres, and the FHIR server are operator-controlled
infrastructure inside it. Error tracking (Sentry) activates only when
`SENTRY_DSN` is set and ships with PII capture off by default.

## Where clinical content can be stored

- **Live cases**: Redis (or in-process memory), expiring via
  `CASE_TTL_SECONDS` (default 1 h).
- **Durable case store** (only when the operator sets `CASE_DB_URL`):
  case snapshots, an append-only event timeline (utterances, HUD
  updates, question feedback), and final reports — this **is** clinical
  content in a database and must be covered by the deployment's
  encryption, access-control, and retention policies. The worker's
  retention cron deletes cases older than `CASE_RETENTION_DAYS`.
  Without `CASE_DB_URL`, nothing conversation-derived is written to
  disk by the application and history endpoints return 503.
- **FHIR write-back**: finalized reports can be posted to the EHR as
  DocumentReference resources — from that point the hospital record
  system owns them.
- **Audit log**: `logs/audit.log` records user, endpoint, patient
  identifier, status, duration — never clinical content.

## Requirements before real PHI

1. **Vendor agreements**: enterprise terms with a BAA (or equivalent) for
   Anthropic and Google AI *before* any PHI reaches `generateContent` /
   the Messages API. Without them, clinical deployments must run with LLM
   features disabled or behind a de-identification layer.
2. **Transport encryption**: TLS at the ALB; internal traffic inside a
   private VPC. No plain-HTTP exposure of the backend
   (`AUTH_COOKIE_SECURE` stays at its default `true`).
3. **At-rest encryption**: EFS (rag_store, caches), ElastiCache, RDS
   (the durable case store), and any log destinations encrypted with
   KMS. The Terraform in `infra/terraform/` provisions these.
4. **Access control**: `APP_MODE=clinical`; `AUTH_SECRET_KEY` resolved
   from a managed source (`core/secrets`: AWS Secrets Manager → env →
   `*_FILE`); per-user accounts via the users registry or, preferably,
   the hospital IdP through `AUTH_MODE=oidc`; role separation
   (clinician/admin). No shared credentials.
5. **Audit**: `logs/audit.log` (JSONL) shipped to durable storage with
   retention per organizational policy. The audit trail is the record of
   who accessed which patient's data and when.
6. **Retention**: define `CASE_TTL_SECONDS`, `CASE_RETENTION_DAYS`, and
   backup policy for the durable store *before* enabling it on real
   data; define retention for anything the operator adds (EHR source,
   log shipping).
7. **Advisory framing**: outputs are constrained to a closed condition
   vocabulary, prescriptive language is filtered from generated questions,
   fallback imaging predictions are labeled as placeholders, and every
   report carries an advisory-only disclaimer. The system is decision
   *support*; it must not be represented as a diagnostic device (which
   would trigger medical-device regulatory pathways).

## Known gaps (tracked, not yet closed)

- No de-identification layer in front of the LLM calls; PHI minimization
  currently relies on prompt construction (summaries, not raw records).
  This is one of the two remaining go-live gates
  (`docs/PRODUCTION_READINESS.md`).
- OIDC scaffolding is stub-verified only; production needs the real IdP
  wired in, plus revocation/refresh semantics and a shorter
  password-mode TTL.
- Audit log shipping/immutability is deployment-specific and not
  automated by this repository.
- The audit middleware attributes patient identifiers from query and path
  parameters; a patient_id inside a JSON/form body (e.g. POST /infer) is
  not parsed at the middleware layer.
