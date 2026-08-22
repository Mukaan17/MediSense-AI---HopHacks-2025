# ADR 0003: /v1 dual-mount instead of a breaking version cutover

Date: 2026-08-22 (backfilled; decision made in R5) · Status: accepted

## Context

The API had no version prefix and one consumer (the bundled frontend).
Introducing versioning by *moving* routes to `/v1` would break every
existing client and script at once.

## Decision

Every router is mounted twice — at its historical root path and under
`/v1`. The security middleware normalizes the prefix so public paths,
rate-limit exemptions, and audit extraction behave identically on both
mounts. New clients target `/v1`; the root mount is compatibility.

## Consequences

- Zero-breakage introduction; the OpenAPI schema documents both mounts.
- A future `/v2` repeats the pattern; the root mount can be retired once
  telemetry shows no traffic.
- Cost: duplicate paths in the schema (accepted — they are generated, not
  maintained).
