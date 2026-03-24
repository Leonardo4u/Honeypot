---
phase: 03-operational-resilience
plan: 02
subsystem: runtime
tags: [scheduler, preflight, logging, diagnostics]
requires: [03-01]
provides:
  - Startup preflight fail-fast for critical runtime prerequisites
  - Minimum schema validation contract for scheduler startup
  - Structured lifecycle logs for boot, preflight, job and cycle totals
affects: [scheduler, database, diagnostics]
tech-stack:
  added: []
  patterns: [fail-fast-preflight, structured-operational-logs, startup-readiness-gate]
key-files:
  created: []
  modified: [scheduler.py, data/database.py]
key-decisions:
  - "Treat missing BOT_TOKEN, CANAL_VIP, DB path/connectivity, and core schema as blocking startup failures"
  - "Keep Excel path check non-critical with warning-only behavior"
patterns-established:
  - "Scheduler startup now emits structured boot and preflight events"
  - "Cycle totals emit stable diagnostics payload for daily triage"
requirements-completed: [OPS-03, OPS-04]
duration: 14 min
completed: 2026-03-24
---

# Phase 3 Plan 02: Preflight and Structured Logging Summary

**Fail-fast startup contract and standardized operational diagnostics across scheduler lifecycle**

## Performance

- **Duration:** 14 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `validar_schema_minimo()` in `data/database.py` to assert required SQLite tables.
- Added `executar_preflight()` in `scheduler.py` with critical checks for `BOT_TOKEN`, `CANAL_VIP`, DB path/connectivity, and schema minimum (`sinais`, `job_execucoes`).
- Enforced fail-fast startup with `raise SystemExit(1)` and actionable failure output on critical preflight errors.
- Added warning-only handling for non-critical Excel path absence.
- Extended structured logs for startup boot (`start`/`ready`), preflight (`start`/`pass`/`failed`), and analysis cycle totals.

## Files Created/Modified
- scheduler.py - Adds startup preflight gate and additional structured operational log milestones.
- data/database.py - Adds minimum schema validation helper used by scheduler preflight.

## Decisions Made
- Critical readiness failures must block scheduler start to avoid silent degraded runtime.
- Observability must remain grep-friendly using stable categories/stages/reason codes.

## Deviations from Plan

None - plan executed as specified.

## Issues Encountered
- `rg` command was unavailable in the environment; verification fallback used `Select-String`.

## User Setup Required

None.

## Next Phase Readiness
- Phase 3 execution artifacts are complete for both plans (03-01 and 03-02).
- Ready for phase-level verification and closure update.

---
*Phase: 03-operational-resilience*
*Completed: 2026-03-24*
