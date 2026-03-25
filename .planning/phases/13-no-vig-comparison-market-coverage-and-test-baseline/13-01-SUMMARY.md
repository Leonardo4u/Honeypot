---
phase: 13-no-vig-comparison-market-coverage-and-test-baseline
plan: 01
subsystem: gate1-no-vig-divergence
tags: [python, filtros, no-vig, gate, regression]
requires:
  - phase: 12-confidence-de-bias-and-quality-prior
    provides: stable confidence/ranking baseline before market divergence update
provides:
  - no-vig divergence comparison in Gate 1
  - backward-compatible fallback when opponent odd is unavailable
  - regression coverage for no-vig and fallback paths
affects: []
tech-stack:
  added: []
  patterns: [bounded divergence threshold, compatibility fallback, reason-code stability]
key-files:
  created: []
  modified: [model/filtros.py, tests/test_filtros_gate.py]
key-decisions:
  - "Gate 1 now computes divergence against no-vig market probability when both sides of the market are available."
  - "If opponent odd is missing/invalid, Gate 1 falls back to legacy implied probability path to preserve compatibility."
  - "Reject reason codes remain mapped to existing gate1 codes to avoid telemetry contract breakage."
patterns-established:
  - "Gate payload supports `odd_oponente_mercado` for market-fair probability normalization."
requirements-completed: [WR-07]
duration: 28min
completed: 2026-03-25
---

# Phase 13 Plan 01 Summary

Implemented no-vig model-vs-market divergence in Gate 1 with deterministic fallback behavior.

## Validation

- python -m unittest tests.test_filtros_gate -v: pass

## Outcome

- Added `calcular_probabilidade_no_vig()` to `model/filtros.py`.
- Updated `gate1_ev_e_odd()` to consume optional `odd_oponente_mercado` and compare divergence against no-vig probability when available.
- Preserved fallback to legacy `1/odd` path when opponent odd is not present.
- Extended `tests/test_filtros_gate.py` with regressions for:
  - explicit no-vig rejection behavior,
  - legacy fallback approval behavior,
  - reason-code stability.

## Files

- model/filtros.py
- tests/test_filtros_gate.py
