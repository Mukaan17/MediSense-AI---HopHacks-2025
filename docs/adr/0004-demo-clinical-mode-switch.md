# ADR 0004: One codebase, a demo/clinical posture switch

Date: 2026-08-22 (backfilled; decision made in P7/P8) · Status: accepted

## Context

The platform must demo all features with synthetic data (open access, EHR
mockups) and also hold a clinical-grade posture (auth required, synthetic
data refused). Two builds would drift; feature flags scattered per
endpoint would leak.

## Decision

A single `APP_MODE` environment switch read *per call* (`core/app_mode`),
enforced in three layers: boot validation (`validate_clinical_config` —
clinical never boots unsigned), the middleware auth gate, and explicit
guards (`_demo_only`, `_guard_synthetic_ehr`) on every demo-only surface.
Synthetic EHR is refused in clinical mode everywhere it could enter
inference.

## Consequences

- Tests flip modes with plain env vars — no module reloads, one app
  object.
- The demo stays a full-featured showcase; clinical mode is the same code
  with the demo affordances provably fenced.
- Real clinical data access arrives via `EHR_SOURCE` implementations
  (FHIR), never by relaxing the synthetic-data guards.
