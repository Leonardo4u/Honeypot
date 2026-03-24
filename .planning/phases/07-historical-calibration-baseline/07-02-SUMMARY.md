---
phase: 07-historical-calibration-baseline
plan: 02
subsystem: calibration
tags: [python, rho, poisson, reporting, model-calibration]
requires:
  - phase: 07-historical-calibration-baseline
    provides: deterministic historical data pipeline from plan 01
provides:
  - per-league rho calibration table
  - baseline-vs-calibrated delta visibility
  - explicit manual operator guidance for rho updates
affects: [08-diagnostic-quality-evaluation, 09-historical-persistence-and-operator-safety]
tech-stack:
  added: []
  patterns: [deterministic league reporting, manual-update guidance, safe no-auto-mutation policy]
key-files:
  created: []
  modified: [calibrar_modelo.py]
key-decisions:
  - "Keep poisson.py as manual update target, not auto-mutated by calibration script."
  - "Sort league reporting explicitly to keep output deterministic across runs."
patterns-established:
  - "Calibration report includes current value, calibrated value, delta, and sample size per league."
  - "Final output always includes explicit next steps and rerun command."
requirements-completed: [CAL-02]
duration: 22min
completed: 2026-03-24
---

# Phase 07: Historical Calibration Baseline Summary

**League-level rho calibration reporting is now deterministic, explicit, and operator-oriented without automatic mutation of model defaults.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-03-24T19:10:00Z
- **Completed:** 2026-03-24T19:32:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Delivered deterministic per-league rho reporting with baseline, calibrated values, delta, and sample-size context.
- Preserved explicit import linkage with poisson calibration primitives (`estimar_rho` and `RHO_POR_LIGA`).
- Clarified post-run guidance so rho updates remain manual and auditable.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build per-league rho calibration report with baseline delta and sample size** - 7848d04
2. **Task 2: Ensure final run guidance clearly directs rho update workflow** - 6fd54f6

## Files Created/Modified
- calibrar_modelo.py - Deterministic rho summary and explicit manual next-step guidance.

## Decisions Made
- Kept all rho updates as manual action in poisson.py to avoid hidden model mutations.
- Added explicit operator guidance line stating no automatic write behavior to poisson.py.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Runtime verification generates heavy output because full calibration flow runs all stages, but execution completed successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Diagnostic phase can reuse stable rho output and calibration run behavior as baseline.
- Historical evaluation work (Brier/win-rate/ROI refinement) is unblocked.

---
*Phase: 07-historical-calibration-baseline*
*Completed: 2026-03-24*
