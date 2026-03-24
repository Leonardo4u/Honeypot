---
phase: 09-historical-persistence-and-operator-safety
plan: 01
subsystem: persistence-safety
tags: [python, sqlite, historico, idempotencia, backfill]
requires:
  - phase: 08-diagnostic-quality-evaluation
    provides: deterministic diagnostics and stable calibration workflow
provides:
  - schema helper for fonte column safety in sinais
  - partial unique index for historico duplicate prevention
  - robust backfill flow with inserted/duplicate/failure counters
affects: []
tech-stack:
  added: []
  patterns: [partial unique index, insert-or-ignore idempotency, row-level failure isolation]
key-files:
  created: [tests/test_historico_backfill.py]
  modified: [data/database.py, calibrar_modelo.py]
key-decisions:
  - "Use partial unique index only for fonte='historico' to avoid blocking regular bot inserts."
  - "Use INSERT OR IGNORE plus explicit counters for duplicate-safe reruns."
patterns-established:
  - "Historical backfill now reports inseridos/duplicados/falhas in one summary line."
  - "Schema safety for historical source tagging is enforced during startup and migration paths."
requirements-completed: [HIST-01, HIST-02, HIST-03]
duration: 28min
completed: 2026-03-24
---

# Phase 09 Plan 01 Summary

Implemented historical persistence hardening with source tagging safety, duplicate-safe reruns, and row-level failure isolation.

## Validation

- python -m unittest tests.test_historico_backfill.TestHistoricoSchemaSafety -v: pass
- python -m unittest tests.test_historico_backfill.TestHistoricoBackfillFlow -v: pass
- python -m py_compile data/database.py calibrar_modelo.py tests/test_historico_backfill.py: pass
- python calibrar_modelo.py: pass

## Outcome

- Added schema helper in data/database.py to guarantee coluna fonte and enforce partial unique index for historical rows.
- Refactored popular_banco_historico to use INSERT OR IGNORE and report inseridos/duplicados/falhas.
- Added dedicated tests for schema migration safety, duplicate blocking, rerun idempotency, and row-level failure isolation.

## Files

- data/database.py
- calibrar_modelo.py
- tests/test_historico_backfill.py
