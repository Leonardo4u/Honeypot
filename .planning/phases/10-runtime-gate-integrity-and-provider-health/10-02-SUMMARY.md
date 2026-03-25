---
phase: 10-runtime-gate-integrity-and-provider-health
plan: 02
subsystem: provider-health-observability
tags: [python, scheduler, odds-ingestion, telemetry, resilience]
requires:
  - phase: 10-runtime-gate-integrity-and-provider-health
    provides: runtime gate baseline and scheduler verification flow
provides:
  - status-aware odds fetch contract with backward-compatible legacy API
  - centralized provider status-to-counter mapping helper
  - scheduler cycle telemetry with complete provider-health category coverage
affects: []
tech-stack:
  added: []
  patterns: [status normalization helper, compatibility wrapper, deterministic status counter tests]
key-files:
  created: [tests/test_scheduler_provider_health.py]
  modified: [data/coletar_odds.py, scheduler.py, tests/test_scheduler_dry_run.py]
key-decisions:
  - "Introduced a structured odds-fetch function that returns both matches and provider status while preserving the legacy list-only function for existing callers."
  - "Provider status normalization and counter updates are centralized to avoid drift between scheduler branches."
  - "Unknown/unexpected statuses are explicitly tracked in `unknown_error` for operational visibility instead of being collapsed."
patterns-established:
  - "Ingestion-layer status metadata is propagated to runtime telemetry through a narrow helper boundary."
  - "Minimal-environment tests stub optional external dependencies to keep verification deterministic."
requirements-completed: [WR-09]
duration: 34min
completed: 2026-03-24
---

# Phase 10 Plan 02 Summary

Implemented provider-health observability with status-aware odds ingestion and complete per-category scheduler telemetry.

## Validation

- python -m unittest tests.test_scheduler_provider_health -v: pass
- python -m unittest tests.test_scheduler_dry_run -v: pass

## Outcome

- Added `buscar_jogos_com_odds_com_status` in `data/coletar_odds.py` to expose retry-layer status metadata to callers.
- Preserved compatibility by keeping `buscar_jogos_com_odds` return shape unchanged (list-only), delegating internally to the new status-aware path.
- Added status normalization and counter update helpers to ensure timeout/http/connection/empty/unknown categories are counted consistently.
- Updated `scheduler.py` to consume status metadata per league request and include `unknown_error` in cycle health summary and telemetry payload.
- Added `tests/test_scheduler_provider_health.py` covering status mapping, empty payload handling, unknown status fallback, and legacy API compatibility.
- Updated `tests/test_scheduler_dry_run.py` with optional dependency stubs (`requests`, `dotenv`) to keep dry-run verification stable in minimal local environments.

## Files

- data/coletar_odds.py
- scheduler.py
- tests/test_scheduler_provider_health.py
- tests/test_scheduler_dry_run.py
