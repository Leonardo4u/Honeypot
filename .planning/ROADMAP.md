# Roadmap: Edge Protocol Bot

## Overview

Harden the existing signal bot in four phases: first stabilize external data ingestion, then improve signal-quality controls, then make runtime operations more resilient, and finally add an automated testing baseline to reduce regression risk.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Data Ingestion Reliability** - Make data inputs resilient and observable.
- [x] **Phase 2: Signal Quality Controls** - Improve gate transparency and threshold consistency.
- [x] **Phase 3: Operational Resilience** - Strengthen scheduler safety and diagnostics.
- [x] **Phase 4: Testing and Verification Baseline** - Add deterministic tests and safe dry-run checks.
 (completed 2026-03-24)
- [ ] **Phase 5: Verification Chain Closure** - Close missing phase-4 verification artifacts and milestone chain consistency gaps.
- [ ] **Phase 6: Requirements and Metadata Reconciliation** - Reconcile requirement traceability and planning metadata with delivered evidence.

## Phase Details

### Phase 1: Data Ingestion Reliability
**Goal**: Make external data ingestion resilient and observable so daily runs degrade gracefully instead of failing hard.
**Depends on**: Nothing (first phase)
**Requirements**: [DATA-01, DATA-02, DATA-03, DATA-04]
**Success Criteria** (what must be TRUE):
	1. Scheduler completes cycles despite partial provider failures.
	2. Failures are categorized with clear operational logs.
	3. Missing or malformed xG/form inputs are handled without crashing analysis.
	4. Data-provider health is summarized each run.
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md: Shared retry/classification boundary for odds and results providers.
- [x] 01-02-PLAN.md: Input validation gates + per-run provider health summary.

### Phase 2: Signal Quality Controls
**Goal**: Improve decision transparency and consistency for gating, thresholds, and stake sizing.
**Depends on**: Phase 1
**Requirements**: [QUAL-01, QUAL-02, QUAL-03, QUAL-04]
**Success Criteria** (what must be TRUE):
	1. Every rejected signal has explicit reason metadata.
	2. Edge/confidence thresholds are centralized and auditable.
	3. Stake sizing always respects bankroll safety caps.
	4. CLV/Brier metrics maintain consistent signal linkage.
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md: Centralize signal policy and structured gate reject metadata.
- [x] 02-02-PLAN.md: Harden Kelly safety guards and CLV/Brier linkage integrity.

### Phase 3: Operational Resilience
**Goal**: Make scheduled automation safer to run continuously with clear diagnostics and startup checks.
**Depends on**: Phase 2
**Requirements**: [OPS-01, OPS-02, OPS-03, OPS-04]
**Success Criteria** (what must be TRUE):
	1. Repeated scheduler windows do not double-process the same work.
	2. Per-game failures do not abort full job batches.
	3. Logs expose critical execution milestones for daily diagnosis.
	4. Missing env/db prerequisites fail fast with actionable messages.
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md: Persistent idempotency registry + guarded scheduler failure isolation.
- [x] 03-02-PLAN.md: Startup preflight fail-fast + structured operational diagnostics.

### Phase 4: Testing and Verification Baseline
**Goal**: Add automated confidence checks for core model, DB writes, and a safe dry-run path.
**Depends on**: Phase 3
**Requirements**: [TEST-01, TEST-02, TEST-03]
**Success Criteria** (what must be TRUE):
	1. Core scoring and gate behavior is covered by deterministic tests.
	2. Database write paths for signals/results have integration-style checks.
	3. End-to-end dry-run can validate flow without sending Telegram messages.
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md: Deterministic unit tests for model analysis and gate reason codes.
- [x] 04-02-PLAN.md: DB integration tests plus no-send scheduler dry-run smoke command.

### Phase 5: Verification Chain Closure
**Goal**: Restore end-to-end milestone verification consistency by adding missing phase-level verification artifacts.
**Depends on**: Phase 4
**Requirements**: [TEST-01, TEST-02, TEST-03]
**Gap Closure**: Closes audit gaps for missing phase-4 verification and milestone verification-chain integration.
**Plans**: 1 plans

Plans:
- [ ] 05-01-PLAN.md: Create and validate phase-4 verification artifact from test/UAT evidence.

### Phase 6: Requirements and Metadata Reconciliation
**Goal**: Reconcile requirement traceability and planning state metadata to match delivered milestone evidence.
**Depends on**: Phase 5
**Requirements**: [DATA-01, DATA-02, DATA-03, DATA-04]
**Gap Closure**: Closes audit drift in REQUIREMENTS/STATE consistency.
**Plans**: TBD

Plans:
- [ ] 06-01: Update traceability/state records and re-baseline milestone metadata.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Ingestion Reliability | 2/2 | Complete | 2026-03-24 |
| 2. Signal Quality Controls | 2/2 | Complete | 2026-03-24 |
| 3. Operational Resilience | 2/2 | Complete | 2026-03-24 |
| 4. Testing and Verification Baseline | 2/2 | Complete   | 2026-03-24 |
| 5. Verification Chain Closure | 0/1 | Not started | - |
| 6. Requirements and Metadata Reconciliation | 0/1 | Not started | - |

---
*Last updated: 2026-03-24 after initialization*
