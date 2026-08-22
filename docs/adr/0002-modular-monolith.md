# ADR 0002: Modular monolith over microservices

Date: 2026-08-22 (backfilled; decision made during the modularization pass) · Status: accepted

## Context

The backend runs STT, retrieval + reranking, imaging, fusion/evidence, and
LLM orchestration. Splitting these into services would let each scale
independently, but the team is small and the operational surface of a
distributed system (service discovery, partial failure, versioned internal
APIs) is expensive.

## Decision

One deployable backend, strictly modularized: `api/` (HTTP surface) may
import `core/` (domain logic); `core/` never imports `api/`. State lives in
`api/state.py` containers mutated in place; mode/auth config is read per
call. Compute-heavy components are extracted to *worker processes* (not
services) when metrics demand it — the module seams are drawn so any
component can be lifted out later without a rewrite.

## Consequences

- Single deploy/rollback unit; the whole test suite runs in-process.
- Scaling is per-container until a component (first candidate: STT) earns
  its own worker; the flag-gated worker design in `docs/ARCHITECTURE.md`
  is the promotion path.
- Revisit when a second team or per-component SLOs arrive.
