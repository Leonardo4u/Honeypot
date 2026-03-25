---
phase: 17-correlation-aware-portfolio-controls
plan: 01
subsystem: ranking-correlation-penalty-and-cap-parameterization
tags: [python, scheduler, ranking, correlation, risk]
requires:
  - phase: 16-gate-robustness-and-steam-noise-filtering
    provides: source-aware gate and per-match cap baseline
provides:
  - same-match correlation penalty in ranking order
  - configurable penalty gradient and per-match cap defaults
  - deterministic regression coverage for concentration reordering
affects: []
tech-stack:
  added: []
  patterns: [correlation-aware ranking score adjustment, deterministic sorting, parameterized concentration controls]
key-files:
  created: []
  modified: [scheduler.py, tests/test_scheduler_quality_prior_ranking.py]
key-decisions:
  - "Ranking now applies progressive same-match penalty before final cap selection to reduce clustered picks."
  - "Penalty step and cap remain parameterized with conservative defaults for operational tuning."
patterns-established:
  - "Concentration controls should act in two layers: score-level soft penalty first, hard cap second."
  - "Ranking transforms must remain deterministic under equal-score conditions."
requirements-completed: [RISK-01]
duration: 31min
completed: 2026-03-25
---

# Phase 17 Plan 01 Summary

Implemented correlation-aware ranking controls to reduce same-match clustering before candidate selection.

## Validation

- python -m unittest tests.test_scheduler_quality_prior_ranking -v: pass

## Outcome

- `scheduler.py` now applies `aplicar_penalizacao_correlacao_ranking` before per-match cap, with configurable penalty step.
- `scheduler.py` keeps cap-by-match as final hard guardrail while preserving deterministic ordering.
- `tests/test_scheduler_quality_prior_ranking.py` now validates escalating penalty behavior and parameterized cap/penalty distribution.
