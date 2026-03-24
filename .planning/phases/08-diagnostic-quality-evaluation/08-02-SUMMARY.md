---
phase: 08-diagnostic-quality-evaluation
plan: 02
subsystem: diagnostics
tags: [python, calibration, win-rate, roi, market-reporting]
requires:
  - phase: 08-diagnostic-quality-evaluation
    provides: structured deterministic Brier diagnostics from plan 01
provides:
  - market-level win-rate and ROI diagnostics for core markets
  - explicit zero-signal output states
  - low-sample quality flags for interpretation safety
affects: [09-historical-persistence-and-operator-safety]
tech-stack:
  added: []
  patterns: [explicit market diagnostics, zero-state transparency, low-sample guardrails]
key-files:
  created: [tests/test_calibrar_modelo_winrate.py]
  modified: [calibrar_modelo.py]
key-decisions:
  - "Keep EV threshold and Poisson math unchanged while improving interpretability signals."
  - "Always print all core markets, including zero-signal states."
patterns-established:
  - "Market diagnostics payload includes quality field (ok, baixa_amostra, sem_sinal)."
  - "Win-rate/ROI reporting contract is now regression-tested."
requirements-completed: [EVAL-03]
duration: 18min
completed: 2026-03-24
---

# Phase 08 Plan 02 Summary

Implemented market-level historical diagnostics with explicit counts, win-rate, ROI, and quality guardrails.

## Validation

- python -m unittest tests.test_calibrar_modelo_winrate -v: pass
- python calibrar_modelo.py: pass

## Outcome

- `calcular_win_rate_historico` now returns structured market metrics including quality flags.
- Report now shows all core markets (`over_2.5`, `1x2_casa`, `1x2_fora`) even with zero signals.
- Added regression tests for metrics presence, zero-state behavior, and audit-friendly return fields.

## Files

- calibrar_modelo.py
- tests/test_calibrar_modelo_winrate.py
