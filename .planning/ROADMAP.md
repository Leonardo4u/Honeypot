# Roadmap: Edge Protocol Bot

## Overview

Milestone v1.1 expands model quality operations through calibration and historical backtesting while preserving the reliability baseline from v1.0.

## Milestones

- [x] v1.0 Reliability and Signal Quality Hardening (shipped 2026-03-24) -> see `.planning/milestones/v1.0-ROADMAP.md`
- [ ] v1.1 Calibracao Estatistica e Backtesting Operacional (active)

## Phases

**Phase Numbering:**
- Integer phases (7, 8, 9): Planned milestone work
- Decimal phases (7.1, 8.1): Urgent insertions (marked with INSERTED)

- [ ] **Phase 7: Historical Calibration Baseline** - Build deterministic ingestion and rho calibration workflow.
- [ ] **Phase 8: Diagnostic Quality Evaluation** - Add reproducible Brier and market-level evaluation outputs.
- [ ] **Phase 9: Historical Persistence and Operator Safety** - Harden historical backfill behavior and usage flow.

## Phase Details

### Phase 7: Historical Calibration Baseline
**Goal**: Establish a reliable calibration pipeline that ingests historical data and estimates per-league rho values.
**Depends on**: Phase 6
**Requirements**: [CAL-01, CAL-02, CAL-03]
**Success Criteria** (what must be TRUE):
	1. Operator can run one command to execute full calibration flow.
	2. League-level rho values are produced with sample-size visibility.
	3. Existing cached CSVs are reused without re-download.
**Plans**: 2 plans

Plans:
- [ ] 07-01-PLAN.md: Historical ingestion/caching pipeline and normalized dataset loading.
- [ ] 07-02-PLAN.md: League-level rho calibration output and operator-facing calibration summary.

### Phase 8: Diagnostic Quality Evaluation
**Goal**: Quantify model historical quality with stable and interpretable diagnostics.
**Depends on**: Phase 7
**Requirements**: [EVAL-01, EVAL-02, EVAL-03]
**Success Criteria** (what must be TRUE):
	1. Historical Brier score runs on reproducible sampling.
	2. Evaluation reports fallback-to-medias ratio as data quality signal.
	3. Win-rate and ROI diagnostics are available for key markets.
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md: Brier workflow and reproducible sampling/reporting guardrails.
- [ ] 08-02-PLAN.md: Market-level win-rate and ROI diagnostics with minimum quality checks.

### Phase 9: Historical Persistence and Operator Safety
**Goal**: Persist useful historical records safely so confidence calibration can consume them without data pollution.
**Depends on**: Phase 8
**Requirements**: [HIST-01, HIST-02, HIST-03]
**Success Criteria** (what must be TRUE):
	1. Historical inserts are source-tagged for downstream filtering.
	2. Duplicate backfill is blocked by idempotent checks.
	3. Row-level failures do not abort batch insertion.
**Plans**: 1 plans

Plans:
- [ ] 09-01-PLAN.md: Historical backfill idempotency and failure-isolation hardening.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 7. Historical Calibration Baseline | 0/2 | Not Started | — |
| 8. Diagnostic Quality Evaluation | 0/2 | Not Started | — |
| 9. Historical Persistence and Operator Safety | 0/1 | Not Started | — |

---
*Last updated: 2026-03-24 after v1.1 roadmap creation*
