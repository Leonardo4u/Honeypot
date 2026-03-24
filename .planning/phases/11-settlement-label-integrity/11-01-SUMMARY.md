---
phase: 11-settlement-label-integrity
plan: 01
subsystem: deterministic-settlement-resolution
tags: [python, settlement, fixtures, sqlite, integrity]
requires:
  - phase: 10-runtime-gate-integrity-and-provider-health
    provides: stable scheduler baseline and deterministic test harness
provides:
  - fixture-id-first settlement resolution contract
  - deterministic date-window fallback for fixture matching
  - sinais schema support for fixture identity persistence
affects: []
tech-stack:
  added: []
  patterns: [id-first resolver, deterministic candidate ranking, idempotent schema guard]
key-files:
  created: [tests/test_settlement_fixture_resolution.py]
  modified: [data/verificar_resultados.py, data/database.py, tests/test_database_integration.py]
key-decisions:
  - "Settlement resolver now prioritizes fixture ID and only falls back to date-window matching when identity is missing."
  - "Fallback matching uses normalized team names plus kickoff proximity sorting for deterministic candidate selection."
  - "Fixture identity fields are persisted in `sinais` through nullable schema columns and update helper."
patterns-established:
  - "Result lookup payload now includes `fixture_id_api`, `fixture_data_api`, and `match_strategy` for traceability."
  - "SQLite schema guards remain idempotent across fresh and existing DB paths."
requirements-completed: [WR-03]
duration: 44min
completed: 2026-03-24
---

# Phase 11 Plan 01 Summary

Implemented deterministic fixture resolution primitives and fixture identity persistence to prevent incorrect settlement matching.

## Validation

- python -m unittest tests.test_settlement_fixture_resolution tests.test_database_integration -v: pass

## Outcome

- Refactored `data/verificar_resultados.py` with a deterministic resolver that:
  - tries fixture lookup by ID first,
  - falls back to a date-window search (+/- 2 days) with deterministic candidate ranking,
  - returns status payload with `fixture_id_api`, `fixture_data_api`, and `match_strategy`.
- Extended `data/database.py` schema guard and table definition with fixture identity columns (`fixture_id_api`, `fixture_data_api`).
- Added `atualizar_fixture_referencia()` helper in `data/database.py` to persist resolver identity safely.
- Added regression tests in `tests/test_settlement_fixture_resolution.py` for id-first behavior, deterministic fallback, and no-match outcome.
- Extended `tests/test_database_integration.py` to verify fixture columns existence and fixture identity persistence helper.

## Files

- data/verificar_resultados.py
- data/database.py
- tests/test_settlement_fixture_resolution.py
- tests/test_database_integration.py
