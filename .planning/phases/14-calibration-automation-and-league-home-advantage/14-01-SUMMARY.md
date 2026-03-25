---
phase: 14-calibration-automation-and-league-home-advantage
plan: 01
subsystem: calibration-runtime-loader
tags: [python, poisson, calibration, dixon-coles, home-advantage]
requires:
  - phase: 13-no-vig-comparison-market-coverage-and-test-baseline
    provides: stable gate/runtime baseline for calibration evolution
provides:
  - automatic persistence of league calibration output
  - runtime consumption of league rho and home advantage with resilient fallback
  - deterministic tests for calibration precedence and write-failure resilience
affects: []
tech-stack:
  added: [data/calibracao_ligas.json]
  patterns: [runtime calibration file contract, cache-backed loader with fallback, safe write warning path]
key-files:
  created: [data/calibracao_ligas.json, tests/test_poisson_calibracao_runtime.py]
  modified: [calibrar_modelo.py, model/poisson.py]
key-decisions:
  - "Calibration output now writes to `data/calibracao_ligas.json` automatically after league rho estimation."
  - "Poisson runtime prioritizes calibration-file league values, then static league map, then default rho."
  - "Home advantage is modeled as league-level multiplier with bounded fallback and compatibility defaults."
patterns-established:
  - "Model parameters can evolve from data artifacts without manual source-code edits."
  - "Calibration write failures are non-fatal and explicitly surfaced by warning logs."
requirements-completed: [CAL-01, CAL-02]
duration: 34min
completed: 2026-03-24
---

# Phase 14 Plan 01 Summary

Implemented automatic calibration persistence and runtime loading for league rho and home-advantage parameters.

## Validation

- python -m unittest tests.test_poisson_calibracao_runtime -v: pass

## Outcome

- `calibrar_modelo.py` now saves calibration outputs to `data/calibracao_ligas.json`.
- `model/poisson.py` now consumes calibration-file parameters with robust fallback behavior.
- Runtime probability output now includes `home_advantage_usado` for observability.
