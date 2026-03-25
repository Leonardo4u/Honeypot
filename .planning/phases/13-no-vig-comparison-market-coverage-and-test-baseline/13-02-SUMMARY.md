---
phase: 13-no-vig-comparison-market-coverage-and-test-baseline
plan: 02
subsystem: runtime-market-coverage-expansion
tags: [python, scheduler, market-coverage, guardrails, ranking]
requires:
  - phase: 13-no-vig-comparison-market-coverage-and-test-baseline
    provides: Gate 1 no-vig contract from plan 01
provides:
  - expanded runtime market matrix
  - gate payload propagation of opponent odds
  - deterministic ranking/runtime regressions for expanded market set
affects: []
tech-stack:
  added: []
  patterns: [declarative market matrix, guardrail preservation, deterministic ranking]
key-files:
  created: []
  modified: [scheduler.py, model/signal_policy.py, tests/test_scheduler_quality_prior_ranking.py]
key-decisions:
  - "Runtime market iteration moved to declarative config with opponent-odd mapping."
  - "Added `1x2_fora` and `under_2.5` without changing MIN_EDGE_SCORE/MIN_CONFIANCA policy gates."
  - "Expanded EV minima in `model/signal_policy.py` to centralize thresholds for broader markets."
patterns-established:
  - "Gate payload now consistently includes `odd_oponente_mercado` for no-vig evaluation."
  - "Scheduler ranking remains deterministic after market expansion."
requirements-completed: [WR-08]
duration: 34min
completed: 2026-03-25
---

# Phase 13 Plan 02 Summary

Expanded scheduler market coverage with guardrails preserved and deterministic runtime regressions passing.

## Validation

- python -m unittest tests.test_scheduler_quality_prior_ranking tests.test_scheduler_runtime_gates -v: pass

## Outcome

- Added declarative runtime market config in `scheduler.py` for:
  - `1x2_casa`
  - `1x2_fora`
  - `over_2.5`
  - `under_2.5`
- Added `listar_mercados_runtime()` helper and expanded human-readable market labels.
- Propagated `odd_oponente_mercado` into gate payload so no-vig logic can be used at runtime.
- Expanded `EV_MINIMO_POR_MERCADO` in `model/signal_policy.py` to include additional market keys.
- Extended scheduler ranking tests to validate:
  - expanded market coverage,
  - opponent-odd payload propagation,
  - deterministic ordering and reject-log context continuity.

## Files

- scheduler.py
- model/signal_policy.py
- tests/test_scheduler_quality_prior_ranking.py
