---
phase: 18-operational-telemetry-and-drift-safeguards
plan: 01
subsystem: weekly-quality-telemetry
tags: [python, telemetry, scheduler, sqlite, brier, win-rate]
requires:
  - phase: 17-correlation-aware-portfolio-controls
    provides: stable ranking/stake risk baseline before long-horizon observability
provides:
  - persistent weekly quality snapshots in SQLite
  - segmented trend series (global + mercado)
  - scheduler weekly integration for automatic telemetry registration
affects: []
tech-stack:
  added: []
  patterns: [idempotent telemetry table, weekly snapshot persistence, scheduler non-blocking observability]
key-files:
  created: [data/quality_telemetry.py, tests/test_quality_telemetry_weekly.py]
  modified: [scheduler.py, scripts/run_tests.py]
key-decisions:
  - "Weekly quality snapshots are persisted in `quality_trends` with unique reference+segment keys for idempotent reruns."
  - "Scheduler weekly stats job now records telemetry after stats/xG refresh without breaking runtime on telemetry errors."
patterns-established:
  - "Long-horizon quality telemetry should be stored as compact weekly snapshots rather than raw event logs."
  - "Weekly maintenance jobs emit structured telemetry logs and degrade gracefully on persistence failures."
requirements-completed: [OBS-01]
duration: 39min
completed: 2026-03-25
---

# Phase 18 Plan 01 Summary

Implemented durable weekly quality telemetry with segmented trend persistence and scheduler integration.

## Validation

- python -m unittest tests.test_quality_telemetry_weekly -v: pass

## Outcome

- `data/quality_telemetry.py` now creates and maintains `quality_trends` snapshots with global/market segments, weekly period boundaries, and idempotent upserts.
- `scheduler.py` weekly maintenance flow now registers quality snapshots after stats/xG updates and logs telemetry context.
- `tests/test_quality_telemetry_weekly.py` validates snapshot persistence, segment coverage, history ordering, and scheduler weekly integration behavior.
- `scripts/run_tests.py` now includes the weekly telemetry suite in canonical baseline runs.
