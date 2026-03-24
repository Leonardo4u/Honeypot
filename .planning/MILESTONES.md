# Milestones

## v1.1 Calibracao Estatistica e Backtesting Operacional (Shipped: 2026-03-24)

**Phases completed:** 3 phases, 5 plans, 11 tasks

**Git range:** `v1.0..30f9546`

**Change size:** 28 files changed, 2345 insertions(+), 57 deletions(-)

**Key accomplishments:**

- Implemented deterministic historical calibration flow with cache-aware ingestion and per-league rho output.
- Added reproducible Brier diagnostics with fallback observability and structured evaluation metadata.
- Added market-level win-rate and ROI diagnostics with sample-quality guardrails and zero-state behavior.
- Hardened historical backfill with `fonte='historico'`, idempotent duplicate blocking, and row-level fault isolation.
- Expanded regression coverage with dedicated tests for Brier workflow, market diagnostics, and historical backfill safety.

**Known technical debt (non-blocking):**

- Milestone audit file for v1.1 was not generated during preflight and should be added in the next governance pass.

---

## v1.0 Reliability and Signal Quality Hardening (Shipped: 2026-03-24)

**Phases completed:** 6 phases, 11 plans, 8 tasks

**Git range:** `3ba5a45..8abb802`

**Change size:** 79 files changed, 4323 insertions(+), 234 deletions(-)

**Key accomplishments:**

- Hardened ingestion reliability with shared retry/classification boundaries for odds and results providers.
- Centralized signal policy and reject metadata, then enforced defensive Kelly and telemetry linkage safeguards.
- Added scheduler fail-fast preflight checks, structured lifecycle diagnostics, and idempotent job-window execution guards.
- Implemented deterministic model/gate tests, DB integration tests, and a no-send dry-run command for safe end-to-end validation.
- Closed verification-chain gaps by adding phase-level verification artifacts and replayed command evidence.
- Reconciled DATA requirement traceability and summary metadata to restore complete milestone audit consistency.

**Known technical debt (non-blocking):**

- Nyquist validation remains partial for legacy phases 01/02 and partial in phase 03.

---
