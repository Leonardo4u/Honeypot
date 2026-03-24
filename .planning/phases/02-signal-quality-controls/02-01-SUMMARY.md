---
phase: 02-signal-quality-controls
plan: 01
subsystem: api
tags: [signal-gating, thresholds, risk-policy]
requires: []
provides:
  - Centralized threshold policy for gate and scheduler
  - Stable reject reason codes for machine-auditable filtering
affects: [scheduler, stake-sizing, telemetry]
tech-stack:
  added: []
  patterns: [centralized-signal-policy, structured-reject-reasons]
key-files:
  created: [model/signal_policy.py]
  modified: [model/filtros.py, scheduler.py]
key-decisions:
  - "Use a dedicated policy module as single threshold source for gate and scheduler"
  - "Add stable reason_code fields to every gate rejection payload"
patterns-established:
  - "Threshold constants should be declared only in model/signal_policy.py"
  - "Gate rejections should always expose bloqueado_em, motivo, reason_code, detalhes"
requirements-completed: [QUAL-01, QUAL-02]
duration: 14 min
completed: 2026-03-24
---

# Phase 2 Plan 01: Signal Policy and Gate Auditability Summary

**Centralized threshold policy with stable reject reason codes across filtering and scheduler consumption**

## Performance

- **Duration:** 14 min
- **Started:** 2026-03-24T15:25:00Z
- **Completed:** 2026-03-24T15:39:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created a single policy source in model/signal_policy.py for confidence, edge, odd bounds, market EV, and reject codes.
- Refactored model/filtros.py to replace literals with policy imports and emit stable reason_code metadata.
- Refactored scheduler.py to consume MIN_EDGE_SCORE and MIN_CONFIANCA from the policy module.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create centralized signal policy module** - aa79d71 (feat)
2. **Task 2: Refactor filtros and scheduler to consume centralized policy** - c8ec49f (feat)

**Plan metadata:** pending

## Files Created/Modified
- model/signal_policy.py - Centralizes gate/scheduler thresholds and reject metadata helpers.
- model/filtros.py - Uses centralized policy values and returns reason_code in rejects.
- scheduler.py - Imports centralized edge/confidence thresholds.

## Decisions Made
- Use model/signal_policy.py as the single source of truth to prevent threshold drift.
- Keep existing numeric defaults to avoid behavior regressions during refactor.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `rg` was unavailable in this environment; acceptance checks were validated with workspace search tooling.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Wave 1 output is complete and unblocks plan 02-02 stake and telemetry integrity hardening.
- No blockers identified for the next wave.

---
*Phase: 02-signal-quality-controls*
*Completed: 2026-03-24*
