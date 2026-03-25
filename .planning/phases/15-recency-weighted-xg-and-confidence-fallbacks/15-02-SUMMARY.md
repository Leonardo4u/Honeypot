---
phase: 15-recency-weighted-xg-and-confidence-fallbacks
plan: 02
subsystem: confidence-fallback-and-sos-caps
tags: [python, confidence, prior, sos, risk-control]
requires:
  - phase: 15-recency-weighted-xg-and-confidence-fallbacks
    provides: recency-weighted xG behavior from plan 01
provides:
  - bounded sem_sinal confidence proxy fallback with traceability fields
  - source-quality-aware SOS clamp ranges (conservative for medias, wide for xG)
  - regression coverage for fallback and adaptive cap behavior
affects: []
tech-stack:
  added: []
  patterns: [bounded proxy fallback, source-quality clamp policy, explicit audit fields]
key-files:
  created: [tests/test_sos_ajuste_caps.py]
  modified: [data/forma_recente.py, data/sos_ajuste.py, tests/test_confidence_quality_prior.py]
key-decisions:
  - "When prior quality is `sem_sinal`, confidence now applies conservative proxy contribution instead of floor-only behavior."
  - "SOS clamping now depends on source quality (`0.85..1.15` for medias, `0.7..1.5` for xG)."
patterns-established:
  - "Fallback logic changes must expose explicit trace fields for observability and downstream audits."
requirements-completed: [CONF-01, MODEL-01]
duration: 31min
completed: 2026-03-24
---

# Phase 15 Plan 02 Summary

Reduced over-cautious confidence behavior for low-signal contexts and made SOS caps adaptive to data source quality.

## Validation

- python -m unittest tests.test_confidence_quality_prior tests.test_sos_ajuste_caps -v: pass

## Outcome

- `calcular_confianca_contexto` now reports and applies bounded proxy fallback when prior is `sem_sinal`.
- SOS adjustment now uses conservative clamping for fallback medias and keeps wider range for trusted xG.
