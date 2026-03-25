---
phase: 16-gate-robustness-and-steam-noise-filtering
plan: 02
subsystem: source-aware-divergence-and-runtime-safeguards
tags: [python, no-vig, divergence, scheduler, telemetry, ranking]
requires:
  - phase: 16-gate-robustness-and-steam-noise-filtering
    provides: gate durability and steam maturity contracts from plan 01
provides:
  - source-quality-aware no-vig application using sharp-bookmaker quality
  - divergence comparison against pre-context base probability
  - per-match market cap in runtime ranking selection
  - fallback/source-quality telemetry counters and minimal drift alert
affects: []
tech-stack:
  added: []
  patterns: [source-quality metadata propagation, pre-context divergence, runtime concentration cap, threshold drift alert]
key-files:
  created: []
  modified: [data/coletar_odds.py, model/analisar_jogo.py, model/filtros.py, scheduler.py, tests/test_filtros_gate.py, tests/test_scheduler_quality_prior_ranking.py, tests/test_scheduler_provider_health.py]
key-decisions:
  - "No-vig normalization now applies only when source quality is sharp; fallback path remains backward-compatible."
  - "Gate divergence now uses `prob_modelo_base` (pre-context) when available."
  - "Runtime candidate selection applies per-match cap to reduce immediate concentration risk."
patterns-established:
  - "Market data quality metadata should be propagated from ingestion to gate payloads."
  - "Operational fallback and drift signals should be emitted from scheduler cycle telemetry."
requirements-completed: [GATE-02, GATE-03]
duration: 41min
completed: 2026-03-24
---

# Phase 16 Plan 02 Summary

Implemented source-aware no-vig/divergence semantics and immediate runtime safeguards for concentration and observability.

## Validation

- python -m unittest tests.test_filtros_gate tests.test_scheduler_quality_prior_ranking tests.test_scheduler_provider_health -v: pass

## Outcome

- `data/coletar_odds.py` now exposes `source_quality` per runtime market based on sharp-bookmaker availability.
- `model/analisar_jogo.py` now returns `prob_modelo_base` for pre-context divergence usage.
- `model/filtros.py` now gates no-vig by source quality and supports base-probability divergence reference.
- `scheduler.py` now applies per-match market cap, tracks missing opponent odds/source-quality fallback counters, and emits minimal drift alert when fallback rate exceeds threshold.
