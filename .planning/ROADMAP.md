# Roadmap: Edge Protocol Bot

**Milestone:** v1 - Reliability and Signal Quality Hardening  
**Created:** 2026-03-24

## Phase 1 - Data Ingestion Reliability

**Goal:** Make external data ingestion resilient and observable so daily runs degrade gracefully instead of failing hard.

**Covers:** DATA-01, DATA-02, DATA-03, DATA-04

**Deliverables:**
- Standardized retry/backoff wrappers for API calls.
- Provider-specific error classification and fallback paths.
- Input validation for xG/form payloads before model execution.
- Data-health summary output per run.

**Definition of Done:**
- Scheduler can complete cycles despite partial provider failures.
- Failures are visible and categorized in logs.

## Phase 2 - Signal Quality Controls

**Goal:** Improve decision transparency and consistency for gating, thresholds, and stake sizing.

**Covers:** QUAL-01, QUAL-02, QUAL-03, QUAL-04

**Deliverables:**
- Gate outputs with structured reject reasons.
- Centralized threshold configuration with change trace.
- Hard safety caps in stake sizing path.
- Consistent CLV/Brier linkage by signal ID.

**Definition of Done:**
- Every signal decision is explainable and auditable.
- No unsafe stake can be emitted from malformed inputs.

## Phase 3 - Operational Resilience

**Goal:** Make scheduled automation safer to run continuously with clear diagnostics and startup checks.

**Covers:** OPS-01, OPS-02, OPS-03, OPS-04

**Deliverables:**
- Idempotent guards for repeated scheduler windows.
- Isolation boundaries around per-game and per-task failures.
- Structured logging for critical workflow milestones.
- Preflight checks for env vars and DB connectivity.

**Definition of Done:**
- Bot tolerates recurring runtime issues without operational collapse.
- Startup fails fast with actionable messages when prerequisites are missing.

## Phase 4 - Testing and Verification Baseline

**Goal:** Add automated confidence checks for core model, DB writes, and a safe dry-run path.

**Covers:** TEST-01, TEST-02, TEST-03

**Deliverables:**
- Deterministic unit tests for scoring/gating logic.
- Integration-style tests for persistence flow.
- Dry-run command to validate end-to-end flow without live messaging.

**Definition of Done:**
- Core logic has repeatable test coverage.
- Regressions are detectable before production runs.

## Notes

- Phases are intentionally ordered to reduce production risk early.
- If urgent defects appear, add an inserted phase before continuing.

---
*Last updated: 2026-03-24 after initialization*
