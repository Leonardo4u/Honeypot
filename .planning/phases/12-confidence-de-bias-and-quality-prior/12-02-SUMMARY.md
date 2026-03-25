---
phase: 12-confidence-de-bias-and-quality-prior
plan: 02
subsystem: runtime-prior-aware-ranking
tags: [python, scheduler, ranking, observability, dry-run]
requires:
  - phase: 12-confidence-de-bias-and-quality-prior
    provides: confidence context and prior contracts from plan 01
provides:
  - prior-aware runtime ranking with bounded score adjustment
  - gate reject telemetry with explicit prior context
  - dry-run compatibility checks for prior-context cycle telemetry
affects: []
tech-stack:
  added: []
  patterns: [bounded prior tie-breaker, deterministic composite sort, quality-context telemetry]
key-files:
  created: [tests/test_scheduler_quality_prior_ranking.py]
  modified: [scheduler.py, tests/test_scheduler_dry_run.py]
key-decisions:
  - "Candidate ordering now uses a bounded prior-aware composite (`score_prior`) while preserving policy thresholds (`MIN_EDGE_SCORE`, `MIN_CONFIANCA`)."
  - "Gate rejections include prior quality metadata for traceable runtime decisions."
  - "Cycle totals telemetry now reports `prior_context_counts` to expose runtime sample-quality distribution."
patterns-established:
  - "Scheduler ranking is deterministic using ordered tuple sort `(score_prior, score, confianca)`."
  - "Weak/empty prior penalizes ordering but does not force hard rejection outside gate rules."
requirements-completed: [WR-06]
duration: 39min
completed: 2026-03-25
---

# Phase 12 Plan 02 Summary

Integrated quality-prior context into scheduler ranking and observability while preserving dry-run/runtime compatibility.

## Validation

- python -m unittest tests.test_scheduler_quality_prior_ranking -v: pass
- python -m unittest tests.test_scheduler_dry_run -v: pass

## Outcome

- Updated `scheduler.py` to consume `calcular_confianca_contexto()` per jogo+mercado and propagate prior fields through candidate payload.
- Added bounded prior ranking adjustment via `calcular_ajuste_prior_ranking()` and deterministic sorting using `score_prior` as top tie-breaker.
- Enriched gate reject logs with prior context (`qualidade_prior`, `amostra_prior`, `prior_ranking`, `ajuste_prior`).
- Added cycle telemetry field `prior_context_counts` for visibility of runtime prior quality states.
- Added `tests/test_scheduler_quality_prior_ranking.py` to verify:
  - deterministic ranking preference for stronger prior,
  - weak prior penalty without forced rejection,
  - reject logs include prior metadata.
- Extended `tests/test_scheduler_dry_run.py` to assert cycle totals include `prior_context_counts`.

## Files

- scheduler.py
- tests/test_scheduler_quality_prior_ranking.py
- tests/test_scheduler_dry_run.py
