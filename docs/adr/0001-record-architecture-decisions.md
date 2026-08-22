# ADR 0001: Record architecture decisions

Date: 2026-08-22 · Status: accepted

## Context

The platform has been through three engineering rounds (remediation P0–P13,
hardening R1–R8, roadmap execution I0+). The load-bearing decisions live in
commit messages and docs that describe *state*, not *why*. New contributors
need the reasoning, not just the result.

## Decision

Keep Architecture Decision Records in `docs/adr/`, numbered, in this
format (Context / Decision / Consequences). A decision that changes gets a
new ADR superseding the old one; ADRs are never edited into a different
decision.

## Consequences

Small write-cost per significant decision; the alternative — re-deriving
intent from git archaeology — has already proven expensive.
