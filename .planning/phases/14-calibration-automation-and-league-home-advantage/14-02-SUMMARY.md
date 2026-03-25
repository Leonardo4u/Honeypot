---
phase: 14-calibration-automation-and-league-home-advantage
plan: 02
subsystem: poisson-over-under-dc-consistency
tags: [python, poisson, dixon-coles, over-under, consistency]
requires:
  - phase: 14-calibration-automation-and-league-home-advantage
    provides: runtime rho/home-advantage parameter resolution
provides:
  - DC-corrected over/under computation using shared corrected matrix
  - normalized over/under probabilities with explicit runtime metadata
  - regression tests for correction impact and legacy signature compatibility
affects: []
tech-stack:
  added: []
  patterns: [shared probability matrix helper, consistency across markets, backward-compatible optional parameters]
key-files:
  created: [tests/test_poisson_over_under_dc.py]
  modified: [model/poisson.py]
key-decisions:
  - "Over/under now reuses the same Dixon-Coles corrected matrix semantics used by 1x2."
  - "Legacy callers remain valid while `liga`/`rho` optional inputs are now supported in over/under."
patterns-established:
  - "Cross-market probability methods share a common correction core to avoid model drift."
requirements-completed: [CAL-03]
duration: 21min
completed: 2026-03-24
---

# Phase 14 Plan 02 Summary

Applied Dixon-Coles consistency to over/under probabilities with deterministic normalization and regression coverage.

## Validation

- python -m unittest tests.test_poisson_over_under_dc -v: pass

## Outcome

- `calcular_prob_over_under` now uses DC-corrected matrix and returns consistent metadata (`rho_usado`, `home_advantage_usado`).
- Probability normalization and correction effect are covered by dedicated tests.
