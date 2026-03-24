---
phase: 08-diagnostic-quality-evaluation
plan: 01
subsystem: diagnostics
tags: [python, calibration, brier, reproducibility, data-quality]
requires:
  - phase: 07-historical-calibration-baseline
    provides: deterministic historical loading and calibration baseline
provides:
  - deterministic Brier sampling contract with explicit seed
  - structured Brier metrics object for downstream verification
  - fallback-to-medias count and percentage as quality signal
affects: [08-02, 09-historical-persistence-and-operator-safety]
tech-stack:
  added: []
  patterns: [deterministic random_state sampling, structured diagnostics return, fallback transparency]
key-files:
  created: [tests/test_calibrar_modelo_brier.py]
  modified: [calibrar_modelo.py]
key-decisions:
  - "Keep Brier formulas unchanged and only harden reproducibility/reporting contract."
  - "Expose fallback ratio both in console output and return payload for automation."
patterns-established:
  - "Calibration diagnostics now return dict payloads instead of scalar-only values."
  - "Determinism is validated by repeated-run tests with fixed random_state."
requirements-completed: [EVAL-01, EVAL-02]
duration: 20min
completed: 2026-03-24
---

# Phase 08 Plan 01 Summary

Implemented deterministic Brier diagnostics and explicit fallback data-quality reporting.

## Validation

- python -m unittest tests.test_calibrar_modelo_brier -v: pass
- python calibrar_modelo.py: pass

## Outcome

- `calcular_brier_historico` now accepts `random_state` and keeps deterministic sampling behavior.
- Brier diagnostics now return structured metrics (`brier_score`, processed count, fallback count/percentage, classification, seed).
- Added regression tests validating deterministic outputs and fallback ratio visibility.

## Files

- calibrar_modelo.py
- tests/test_calibrar_modelo_brier.py
