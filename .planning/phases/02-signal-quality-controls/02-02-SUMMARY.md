---
phase: 02-signal-quality-controls
plan: 02
subsystem: database
tags: [kelly, clv, brier, safety-guards]
requires:
  - phase: 02-01
    provides: central policy and structured gating metadata
provides:
  - Defensive Kelly validation with malformed-input rejection
  - Signal linkage integrity checks for CLV/Brier writes
  - Idempotent duplicate closure protection in telemetry updates
affects: [scheduler, telemetry, bankroll]
tech-stack:
  added: []
  patterns: [defensive-input-validation, linkage-integrity-guards, idempotent-close-updates]
key-files:
  created: []
  modified: [data/kelly_banca.py, scheduler.py, data/clv_brier.py, data/database.py]
key-decisions:
  - "Reject malformed Kelly inputs with stable motivo codes before stake math"
  - "Guard CLV/Brier writes and updates with explicit sinal_id existence checks"
patterns-established:
  - "Kelly outputs must never propagate NaN/negative stake values"
  - "Closure updates in tracking modules should be idempotent"
requirements-completed: [QUAL-03, QUAL-04]
duration: 18 min
completed: 2026-03-24
---

# Phase 2 Plan 02: Stake Safety and Tracking Integrity Summary

**Defensive Kelly stake guards and idempotent CLV/Brier linkage validation for safer post-result telemetry**

## Performance

- **Duration:** 18 min
- **Started:** 2026-03-24T15:40:00Z
- **Completed:** 2026-03-24T15:58:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Hardened data/kelly_banca.py with explicit numeric validation, range guards, and non-negative finite stake enforcement.
- Added scheduler safe-skip handling for malformed Kelly payloads to preserve loop continuity.
- Added database helper for sinal_id existence and enforced linkage checks + idempotent closure behavior in data/clv_brier.py.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add malformed-input-safe guards to kelly sizing path** - 0e310ee (fix)
2. **Task 2: Enforce CLV/Brier signal linkage integrity** - 093a1cc (fix)

**Plan metadata:** pending

## Files Created/Modified
- data/kelly_banca.py - Adds strong input and output safety guards around stake calculation.
- scheduler.py - Safely rejects malformed Kelly responses without interrupting processing.
- data/database.py - Exposes sinal_existe helper for linkage checks.
- data/clv_brier.py - Validates signal linkage before writes and avoids duplicate closure corruption.

## Decisions Made
- Keep guard behavior conservative: malformed input blocks stake generation rather than trying implicit coercion.
- Return existing CLV/Brier values on duplicate closure attempts to keep updates idempotent.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 2 quality-control scope is complete with policy centralization and telemetry integrity hardening.
- Ready for phase-level verification and transition to Phase 3 planning/execution.

---
*Phase: 02-signal-quality-controls*
*Completed: 2026-03-24*
