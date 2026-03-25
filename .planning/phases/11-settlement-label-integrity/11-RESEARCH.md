# Phase 11 Research - Settlement Label Integrity

## Scope

Phase 11 addresses WR-03 and WR-04:
- WR-03: deterministic settlement matching (fixture id and/or date-safe fallback)
- WR-04: pending-bet settlement must not rely on same-day lookup

## Current Behavior (Observed)

- Pending settlements in scheduler iterate all `status='pendente'` rows and call `buscar_resultado_jogo(time_casa, time_fora)` with no date argument.
- `buscar_resultado_jogo` defaults `date=today` and scans one day of fixtures only.
- Team matching is substring-based (`in` checks), which can mislabel similarly named teams.

## Risks

- Wrong fixture can be matched when same teams/similar names appear in multiple competitions.
- Older pending bets are skipped indefinitely because the lookup is constrained to `today`.
- Settlement decisions are not traceable to a stable fixture identifier.

## Recommended Technical Direction

1. Add deterministic fixture identity support in persistence
- Extend `sinais` schema with nullable settlement identity fields:
  - `fixture_id_api` (TEXT)
  - `fixture_data_api` (TEXT)
- Keep migration idempotent via schema guard helper.

2. Build resolver that prefers fixture id, then deterministic fallback
- In `data/verificar_resultados.py`, add a resolver flow:
  - If `fixture_id_api` exists: query fixture by id first.
  - Else: query a date window around scheduled kickoff (for example -2 to +2 days).
  - Score candidates by exact team normalization + kickoff proximity to stored `horario`.
  - Return structured payload with `fixture_id`, `fixture_date`, `match_strategy`, `status`.

3. Make scheduler settlement date-safe and idempotent
- Replace naive `today` lookup with resolver inputs from persisted signal context (`jogo`, `liga`, `horario`, `fixture_id_api`).
- Persist resolved fixture identity as soon as a deterministic match is found, even before final status.
- Keep final result update idempotent and preserve existing side effects (bankroll, Brier, reactions, Excel).

## Testing Implications

- Add deterministic unit tests for fixture resolution and fallback ordering using mocked API responses.
- Add DB integration tests for new columns/migration behavior.
- Add scheduler settlement tests for cross-day pending handling and fixture-id reuse.

## Discovery Level

Level 0 (existing stack and patterns only):
- No new external dependency required.
- Changes are localized to existing scheduler/data modules and test suite.
