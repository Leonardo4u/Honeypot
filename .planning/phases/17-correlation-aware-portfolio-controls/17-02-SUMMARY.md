---
phase: 17-correlation-aware-portfolio-controls
plan: 02
subsystem: kelly-same-match-correlation-reducer
tags: [python, kelly, scheduler, bankroll, correlation]
requires:
  - phase: 17-correlation-aware-portfolio-controls
    provides: ranking concentration controls from plan 01
provides:
  - Kelly reducer factor for same-match open exposure
  - scheduler-to-kelly propagation of same-match pending signal context
  - unit and integration regressions for correlation-aware stake sizing
affects: []
tech-stack:
  added: []
  patterns: [layered stake guardrails, optional backward-compatible Kelly parameter, scheduler risk-context propagation]
key-files:
  created: [tests/test_kelly_banca_correlation.py]
  modified: [data/kelly_banca.py, scheduler.py, tests/test_scheduler_quality_prior_ranking.py]
key-decisions:
  - "Kelly now applies an additional same-match correlation multiplier on top of existing exposure guardrails."
  - "Scheduler computes and forwards same-match pending signal count to Kelly at call time."
patterns-established:
  - "Risk multipliers should be explicit in payload (`fator_correlacao_mesmo_jogo`) for traceability."
  - "Scheduler integration tests should assert context propagation into Kelly call arguments."
requirements-completed: [RISK-02]
duration: 36min
completed: 2026-03-25
---

# Phase 17 Plan 02 Summary

Implemented same-match correlation reduction in Kelly sizing and wired correlation context from scheduler runtime into stake calculation.

## Validation

- python -m unittest tests.test_kelly_banca_correlation -v: pass
- python -m unittest tests.test_scheduler_quality_prior_ranking -v: pass

## Outcome

- `data/kelly_banca.py` now includes `fator_reducao_correlacao_mesmo_jogo`, accepts `sinais_mesmo_jogo_abertos`, and returns `fator_correlacao_mesmo_jogo` in approved payloads.
- `data/kelly_banca.py` now exposes `contar_sinais_mesmo_jogo_abertos(jogo)` for runtime correlation context.
- `scheduler.py` now forwards same-match pending-signal counts into `calcular_kelly(...)`.
- Added `tests/test_kelly_banca_correlation.py` for Kelly-specific correlation behavior and output-contract coverage.
- Updated `tests/test_scheduler_quality_prior_ranking.py` to assert scheduler propagation of same-match context to Kelly.
