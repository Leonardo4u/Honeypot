# Phase 10 Research: Runtime Gate Integrity and Provider Health

## Problem Snapshot

Current runtime flow in scheduler still neutralizes key protections:

- Gate 2 receives fixed `escalacao_confirmada=True`.
- Gate 3 receives fixed `variacao_odd=0.0`.
- Gate 4 receives fixed `sinais_hoje=0` during candidate filtering.
- Provider health dictionary declares `timeout` and `http_error`, but the collection path only increments `ok`, `empty_payload`, `invalid_input`, `fallback_used`, and broad `connection_error`.

This weakens hit-rate governance because runtime selection can bypass intended reject paths and hides provider degradation categories needed for operational decisions.

## Code Evidence

- `scheduler.py`
- `model/filtros.py`
- `data/coletar_odds.py`
- `data/ingestion_resilience.py`
- `tests/test_filtros_gate.py`
- `tests/test_scheduler_dry_run.py`

## Constraints

- Preserve existing Gate API contracts in `model/filtros.py` where possible.
- Keep dry-run mode (`processar_jogos(dry_run=True)`) deterministic and Telegram-free.
- Avoid broad behavior drift in model formulas and ranking beyond gate-context correctness.
- Keep fallback behavior tolerant when certain runtime context (for example lineup feed) is unavailable.

## Proposed Phase 10 Split

### Plan 10-01 (wave 1)
Restore real runtime gate context with explicit helper functions in scheduler.

- Compute dynamic daily signal count at gate time.
- Infer lineup confirmation from available kickoff/context data without hardcoded `True`.
- Derive odd variation from steam/opening snapshot when available instead of fixed `0.0`.
- Add targeted tests for gate payload construction and limit enforcement path.

### Plan 10-02 (wave 2)
Complete provider-health categorization from ingestion outcome statuses.

- Return ingestion metadata from odds collection flow.
- Map provider statuses (`ok`, `timeout`, `http_error`, `connection_error`, `empty_payload`, `unknown_error`) into cycle telemetry.
- Preserve existing aggregate summary output and `log_event` payload shape.
- Add tests validating per-status counter increments and no silent drops.

## Risks and Mitigations

- Risk: lineup signal source is not yet integrated.
  - Mitigation: introduce explicit `lineup_status` state (`confirmed`, `unavailable`, `unknown`) and conservative gate mapping with reason logging.
- Risk: steam/opening data absent for some matches.
  - Mitigation: keep safe default `variacao_odd=0.0` only when snapshot truly unavailable, and mark reason in analysis diagnostics.
- Risk: telemetry changes could break existing dry-run assertions.
  - Mitigation: extend tests by asserting required keys and stable totals, not brittle full-string matches.

## Exit Criteria for Phase 10

- WR-01 complete: runtime gates consume non-placeholder inputs.
- WR-02 complete: daily-limit gate uses real count and reason codes surface in logs.
- WR-09 complete: provider health summary consistently categorizes status classes for each league fetch cycle.
