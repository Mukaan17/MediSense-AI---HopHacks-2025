# Changelog

Notable changes by engineering round. Package-level detail lives in the
plan documents (`docs/MASTER_PLAN.md`, `docs/IMPLEMENTATION_PLAN.md`) and
per-commit messages.

## Unreleased — roadmap execution (I-series)

- I0: CODEOWNERS, PR template, ADRs (`docs/adr/`), this changelog.

## Hardening round (R1–R8), 2026-08

- One `parse_llm_json` with golden-fixture tests replaces four copy-pasted
  LLM JSON salvage blocks.
- Prompt templates render through real Jinja2 (`StrictUndefined`).
- RAG store migrated pickle → JSON (deserialization class removed).
- Decomposition round 2: `api/routes/ws.py` split from `cases.py`,
  `core/diagnosis/` package, frontend `useLiveCase` hook +
  `LiveAnalysisPanel`.
- Typed response models + `/v1` dual-mount with prefix-normalized policy.
- Coverage in CI, Dependabot, advisory pip-audit/npm-audit job,
  python-jose CVE upgrade, retrieval recall@5 eval, WS load baseline
  (`docs/PERF_BASELINE.md`).
- Playwright E2E smoke (demo + clinical) — first run caught and fixed two
  production bugs (FormData content-type; error-object toast crash).
- Runbook, Prometheus alert rules, `llm_errors` metric, frontend
  `strict: true`.

## Remediation roadmap (P0–P13), 2026-08

- RAG chunking + metadata; cross-encoder re-ranking.
- True token streaming for the live coach; deep final report; model
  routing via `config/models.yaml` with fallback.
- Server-side live STT (AudioWorklet PCM → `/ws/transcribe`, energy VAD).
- Demo/clinical mode switch; JWT auth with WS tickets; security
  middleware (request IDs, upload caps, rate limiting, audit log).
- Redis-backed case store option; CI gates; CPU Docker + compose + ECS
  deployment docs; `/metrics`; compliance notes.

## Pre-remediation (hackathon baseline), 2025-09

- Original HopHacks build: FastAPI monolith, CRA frontend, FAISS KB,
  BiomedCLIP imaging, WhisperX voice, Gemini-based advisory pipeline.
