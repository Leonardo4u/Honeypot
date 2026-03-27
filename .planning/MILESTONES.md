# Milestones

## v1.3 Calibration Freshness and Portfolio Risk Controls (Shipped: 2026-03-25)

**Phases completed:** 5 phases, 10 plans

**Git range:** `a5960ad..9f82d17`

**Change size:** 128 files changed, 12489 insertions(+), 522 deletions(-)

**Key accomplishments:**

- Operationalized league-aware calibration freshness with automatic rho/home-advantage runtime consumption.
- Aligned over/under behavior with Dixon-Coles low-score consistency and added dedicated regression safety.
- Added recency-weighted xG and stronger confidence fallback controls for low-sample contexts.
- Hardened gate robustness with persistent standings cache, source-aware no-vig checks, and steam maturation safeguards.
- Reduced concentration risk with correlation-aware ranking penalties and same-match Kelly stake reduction.
- Expanded operations telemetry with weekly persisted trends, configurable settlement windows, and rolling drift alerts.

**Known technical debt (non-blocking):**

- Continue monitoring weekly drift segments through at least one full settlement cycle before tightening alert thresholds.

---

## v1.2 Win Rate Integrity and Runtime Quality (Shipped: 2026-03-25)

**Phases completed:** 4 phases, 9 plans

**Git range:** `3d2f8ff..a5960ad`

**Change size:** 39 files changed, 3303 insertions(+), 268 deletions(-)

**Key accomplishments:**

- Restored runtime gate integrity with real lineup/odd-variation/daily-count inputs and explicit reject reason telemetry.
- Implemented status-aware provider health categorization for timeout/http/connection/empty payload paths in cycle metrics.
- Made settlement deterministic across pending days using fixture-id-first resolution with date-safe fallback matching.
- Added confidence de-bias and league+market quality-prior context to runtime ranking with deterministic ordering safeguards.
- Replaced raw 1/odd divergence checks with no-vig market probability and propagated opponent odd payloads in scheduler gates.
- Established reproducible local validation with pinned dependencies and canonical one-command test execution.

**Known technical debt (non-blocking):**

- Milestone audit file for v1.2 was not generated during preflight and should be added in a governance pass (`/gsd-audit-milestone`).

---

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
