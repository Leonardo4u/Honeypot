# Roadmap: Edge Protocol Bot

## Overview

Milestone v1.2 focuses on win-rate integrity: effective runtime gates, clean settlement labels, confidence de-biasing, and market-quality-aware selection.

## Scope Additions (2026-03-24)

- Restore real gate inputs for lineup, odd variation, and daily-limit enforcement in runtime.
- Make settlement deterministic across pending bets with fixture/date-safe resolution.
- Reduce confidence bias from self-selected signal history.
- Inject historical market+league quality prior into runtime selection.
- Replace raw 1/odd market comparison with no-vig probability.
- Expand market coverage with hit-rate-first guardrails.
- Complete provider-health observability and reproducible test baseline.

## Milestones

- [x] v1.0 Reliability and Signal Quality Hardening (shipped 2026-03-24) -> see `.planning/milestones/v1.0-ROADMAP.md`
- [x] v1.1 Calibracao Estatistica e Backtesting Operacional (shipped 2026-03-24) -> see `.planning/milestones/v1.1-ROADMAP.md`
- [ ] v1.2 Win Rate Integrity and Runtime Quality (active)

## Active Milestone

v1.2 Win Rate Integrity and Runtime Quality

## Phases

- [x] **Phase 10: Runtime Gate Integrity and Provider Health** - Restore effective gate inputs and complete health telemetry coverage.
- [x] **Phase 11: Settlement Label Integrity** - Make pending-signal closure deterministic and date-safe.
- [ ] **Phase 12: Confidence De-bias and Quality Prior** - Remove confidence selection bias and apply market/league quality prior at runtime.
- [ ] **Phase 13: No-vig Comparison, Market Coverage, and Test Baseline** - Upgrade market probability comparison, expand coverage, and lock reproducible tests.

## Phase Details

### Phase 10: Runtime Gate Integrity and Provider Health
**Goal**: Ensure gates 2/3/4 and health telemetry use real runtime values.
**Depends on**: Phase 9
**Requirements**: [WR-01, WR-02, WR-09]
**Success Criteria**:
	1. Gate 2/3/4 consume non-placeholder runtime inputs.
	2. Daily limit gate reflects real sent-signal count.
	3. Provider health counters report categorized timeout/http/connection/empty results.

### Phase 11: Settlement Label Integrity
**Goal**: Prevent wrong result assignment and stale day-only lookups.
**Depends on**: Phase 10
**Requirements**: [WR-03, WR-04]
**Success Criteria**:
	1. Pending bets can be settled beyond same-day lookup.
	2. Match resolution is deterministic and traceable.
	3. Settlement path preserves idempotency and explicit failure reasons.

### Phase 12: Confidence De-bias and Quality Prior
**Goal**: Make confidence less self-referential and selection quality-aware.
**Depends on**: Phase 11
**Requirements**: [WR-05, WR-06]
**Plans:** 2 plans
Plans:
- [ ] 12-01-PLAN.md - Debiased confidence foundation and market+league quality-prior contract.
- [ ] 12-02-PLAN.md - Runtime ranking integration with quality-prior observability and dry-run compatibility.
**Success Criteria**:
	1. Confidence avoids pure self-selected signal feedback loops.
	2. Runtime candidate ranking includes market+league quality prior with sample guardrails.
	3. Selection quality state is observable in logs/reporting fields.

### Phase 13: No-vig Comparison, Market Coverage, and Test Baseline
**Goal**: Improve market comparison fidelity and reproducible iteration speed.
**Depends on**: Phase 12
**Requirements**: [WR-07, WR-08, WR-10]
**Success Criteria**:
	1. Divergence checks use no-vig market probabilities.
	2. Runtime supports additional market paths under hit-rate guardrails.
	3. Tests run via one reproducible command with pinned dependencies.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 10. Runtime Gate Integrity and Provider Health | 2/2 | Completed | 2026-03-24 |
| 11. Settlement Label Integrity | 2/2 | Completed | 2026-03-24 |
| 12. Confidence De-bias and Quality Prior | 0/2 | Planned | - |
| 13. No-vig Comparison, Market Coverage, and Test Baseline | 0/0 | Planned | - |

## Next Step

Run `/gsd-plan-phase 12` to create confidence de-bias and quality-prior plans.

---
*Last updated: 2026-03-24 after phase 11 execution completion*
