## What

<!-- One or two sentences: what does this change do? -->

## Why

<!-- The problem or roadmap item this addresses. Link docs/IMPROVEMENT_ROADMAP.md / issues where relevant. -->

## Verification

- [ ] `pytest tests/ -q` green
- [ ] `ruff check .` clean
- [ ] Frontend: `tsc --noEmit`, unit tests, production build green
- [ ] E2E (`e2e/demo`, `e2e/clinical`) green if the change touches API contract, auth, or UI flows
- [ ] Docs updated where behavior changed (`docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, ...)

## Risk & rollback

<!-- What could this break, and how is it reverted? -->
