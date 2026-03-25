---
phase: 12-confidence-de-bias-and-quality-prior
plan: 01
subsystem: confidence-debias-foundation
tags: [python, confidence, prior, sqlite, telemetry]
requires:
  - phase: 11-settlement-label-integrity
    provides: deterministic runtime/settlement baseline for safe signal-quality evolution
provides:
  - league+market quality-prior computation contract
  - debiased confidence context with sample-aware provenance
  - deterministic tests for prior quality states and confidence compatibility
affects: []
tech-stack:
  added: []
  patterns: [sample-aware prior states, bounded prior contribution, backward-compatible confidence wrapper]
key-files:
  created: [data/quality_prior.py, tests/test_confidence_quality_prior.py]
  modified: [data/database.py, data/forma_recente.py]
key-decisions:
  - "Confidence context now exposes provenance (`origem`, `qualidade_prior`, `amostra_prior`) while keeping `calcular_confianca_dados` numeric compatibility."
  - "Market+league prior uses bounded confidence/ranking contribution with explicit states (`sem_sinal`, `baixa_amostra`, `ok`)."
  - "Optional dependency loading (`dotenv`) is fail-safe for test/runtime environments without python-dotenv."
patterns-established:
  - "Import paths in data modules support package and script execution modes."
  - "Confidence APIs now separate context-rich contract from compatibility wrapper."
requirements-completed: [WR-05]
duration: 46min
completed: 2026-03-25
---

# Phase 12 Plan 01 Summary

Implemented the confidence de-bias foundation with explicit league+market quality prior and sample-aware confidence context.

## Validation

- python -m unittest tests.test_confidence_quality_prior -v: pass

## Outcome

- Added `buscar_metricas_qualidade_liga_mercado()` in `data/database.py` to aggregate finalized historical quality metrics by liga+mercado.
- Added `data/quality_prior.py` with bounded prior contract and quality states (`sem_sinal`, `baixa_amostra`, `ok`).
- Refactored `data/forma_recente.py`:
  - introduced `calcular_confianca_contexto()` with provenance fields and prior integration,
  - preserved `calcular_confianca_dados()` compatibility returning numeric confidence,
  - added `carregar_medias_safe()` and optional `dotenv` loading fallback for environment compatibility.
- Added deterministic regression tests in `tests/test_confidence_quality_prior.py` covering:
  - prior state transitions,
  - positive ranking prior for healthy samples,
  - compatibility contract between context-rich and numeric confidence APIs.

## Files

- data/database.py
- data/quality_prior.py
- data/forma_recente.py
- tests/test_confidence_quality_prior.py
