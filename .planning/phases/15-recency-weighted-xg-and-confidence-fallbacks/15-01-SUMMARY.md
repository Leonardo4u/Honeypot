---
phase: 15-recency-weighted-xg-and-confidence-fallbacks
plan: 01
subsystem: xg-temporal-decay
tags: [python, understat, xg, recency, weighting]
requires:
  - phase: 14-calibration-automation-and-league-home-advantage
    provides: stable poisson/DC baseline before xG freshness adjustments
provides:
  - exponential temporal weighting in xG historical aggregation
  - preserved output contract for media calculation API
  - deterministic regressions for recency weighting behavior
affects: []
tech-stack:
  added: []
  patterns: [exponential decay helper, chronological weighting, backward-compatible API]
key-files:
  created: [tests/test_xg_understat_decay.py]
  modified: [data/xg_understat.py]
key-decisions:
  - "Applied exponential temporal decay (`decay_base=0.9`) to prioritize recent Understat matches."
  - "Kept `calcular_media_gols_com_xg` return contract unchanged to avoid scheduler/model integration breakage."
patterns-established:
  - "Statistical freshness updates should be introduced via isolated helpers and verified with deterministic unit tests."
requirements-completed: [XGF-01]
duration: 24min
completed: 2026-03-24
---

# Phase 15 Plan 01 Summary

Implemented recency-weighted xG aggregation using exponential temporal decay while preserving integration contracts.

## Validation

- python -m unittest tests.test_xg_understat_decay -v: pass

## Outcome

- `data/xg_understat.py` now computes weighted xG means with higher influence from recent matches.
- Existing callers continue to consume the same `(media_casa, media_fora, fonte)` contract.
