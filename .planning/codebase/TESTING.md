# Testing Patterns

**Analysis Date:** 2026-03-25

## Test Framework

**Runner:**
- Framework: `unittest` (stdlib).
- Config: no external config file; suites are module-driven.

**Assertion Library:**
- `unittest.TestCase` assertions (`assertEqual`, `assertTrue`, `assertIn`, etc.).

**Canonical Command (v1.2 baseline):**
```bash
python scripts/run_tests.py
```

## Test File Organization

**Location:**
- Primary automated suites under `tests/` with `test_*.py` naming.
- Fixtures in `tests/fixtures/`.

**Representative suites:**
- `tests/test_filtros_gate.py`
- `tests/test_scheduler_runtime_gates.py`
- `tests/test_scheduler_dry_run.py`
- `tests/test_scheduler_provider_health.py`
- `tests/test_settlement_fixture_resolution.py`
- `tests/test_scheduler_settlement_integrity.py`
- `tests/test_confidence_quality_prior.py`
- `tests/test_scheduler_quality_prior_ranking.py`
- `tests/test_database_integration.py`

Baseline run excludes unstable model-simulation suites that currently depend on full scientific stack parity.

## Test Structure

**Suite execution contract:**
- `scripts/run_tests.py` loads deterministic module list and returns non-zero exit on any failure.
- Individual suite execution remains supported via `python -m unittest <module> -v`.

## Mocking Patterns

- `unittest.mock.patch` is used for external boundaries and runtime side effects:
  - Telegram client
  - odds/API providers
  - scheduler gateways
  - sqlite connection boundaries (where needed)
- Dependency stubs for optional packages are injected in scheduler tests (`schedule`, `telegram`, `numpy`, `scipy`, `requests`, `dotenv`) to keep tests deterministic in minimal environments.

## Test Types

**Unit/Contract:**
- Gate logic and reason-code stability (`tests/test_filtros_gate.py`).
- Runtime gate context helpers (`tests/test_scheduler_runtime_gates.py`).

**Integration-focused deterministic runtime checks:**
- Dry-run behavior and telemetry (`tests/test_scheduler_dry_run.py`).
- Settlement matching and cross-day integrity (`tests/test_settlement_fixture_resolution.py`, `tests/test_scheduler_settlement_integrity.py`).
- Confidence/prior contracts and scheduler ranking behavior (`tests/test_confidence_quality_prior.py`, `tests/test_scheduler_quality_prior_ranking.py`).

## Developer Commands

```bash
python scripts/run_tests.py
python -m unittest tests.test_filtros_gate -v
python -m unittest tests.test_scheduler_quality_prior_ranking -v
python -m unittest tests.test_scheduler_dry_run -v
```

---

*Testing analysis updated: 2026-03-25 (phase 13 baseline)*
