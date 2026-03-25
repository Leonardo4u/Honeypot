---
phase: 18-operational-telemetry-and-drift-safeguards
plan: 02
subsystem: settlement-window-profiles-and-rolling-drift-alerts
tags: [python, settlement, drift, scheduler, telemetry, alerts]
requires:
  - phase: 18-operational-telemetry-and-drift-safeguards
    provides: persisted weekly snapshots from plan 01
provides:
  - competition-profile settlement windows
  - league-context propagation from scheduler to settlement resolver
  - rolling drift detection on weekly historical snapshots with Telegram alert dispatch
affects: []
tech-stack:
  added: []
  patterns: [profile-based settlement windows, fixture-id-first with configurable fallback breadth, sustained-drift alerting]
key-files:
  created: []
  modified: [data/verificar_resultados.py, data/quality_telemetry.py, scheduler.py, tests/test_settlement_fixture_resolution.py, tests/test_scheduler_settlement_integrity.py, tests/test_quality_telemetry_weekly.py]
key-decisions:
  - "Settlement date-window fallback is now competition-aware (wider for UEFA profiles) while keeping default behavior for unknown leagues."
  - "Rolling drift alert only triggers on sustained degradation windows, reducing one-cycle noise alerts."
  - "Drift rolling alerts are sent to Telegram VIP channel when sustained threshold breach is detected."
patterns-established:
  - "Settlement resilience should combine fixture-id-first matching with profile-tuned date windows."
  - "Operational drift alerts should require persistence across multiple snapshots before escalation."
requirements-completed: [SETTLE-01, OBS-02]
duration: 44min
completed: 2026-03-25
---

# Phase 18 Plan 02 Summary

Implemented competition-profile settlement windows and rolling drift safeguards with scheduler-level alerting.

## Validation

- python -m unittest tests.test_settlement_fixture_resolution tests.test_scheduler_settlement_integrity -v: pass
- python -m unittest tests.test_quality_telemetry_weekly -v: pass

## Outcome

- `data/verificar_resultados.py` now exposes configurable settlement windows per competition profile and applies them in date-window fallback matching.
- `scheduler.py` now passes `liga` context into settlement resolution and supports weekly rolling drift evaluation + alert dispatch.
- `data/quality_telemetry.py` now evaluates sustained rolling drift over historical weekly snapshots.
- Settlement and scheduler integration regressions were expanded to validate league-aware window behavior and context propagation.
