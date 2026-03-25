# Phase 12 Research - Confidence De-bias and Quality Prior

## Scope

Phase 12 addresses WR-05 and WR-06:
- WR-05: reduce confidence bias from self-selected bet history and use explicit quality priors
- WR-06: add historical market+league quality prior into runtime candidate ranking/filtering

## Current Behavior (Observed)

- Runtime confidence is built in `data/forma_recente.py` via `calcular_confianca_dados(time_casa, time_fora)`.
- Calibrated confidence uses `data/database.py:calcular_confianca_calibrada` based on `buscar_historico_time`, which currently reads only finalized signals where a team appears in previously selected bets.
- Runtime selection in `scheduler.py` ranks candidates mostly by adjusted `edge_score` (`steam_bonus` + gate penalty), then slices top N.
- No explicit market+league historical prior is injected into ranking or filter payload.

## Risks

- Confidence is partially self-referential because historical samples come from already-selected signals, amplifying selection bias.
- New/under-sampled market+league combinations are treated similarly to well-measured combinations.
- Candidate ranking does not explicitly downweight low-quality historical slices.

## Recommended Technical Direction

1. Introduce explicit quality-prior computation layer
- Add a small helper module (for example `data/quality_prior.py`) that computes market+league quality from `sinais` historical outcomes.
- Include sample-aware states (`ok`, `baixa_amostra`, `sem_sinal`) and a normalized prior contribution.
- Reuse existing quality semantics already seen in calibration outputs (`calibrar_modelo.py`).

2. De-bias confidence calculation
- Extend confidence contract to return both score and provenance/components (base coverage, sample sufficiency, prior contribution).
- Replace purely team-selected-history dependence with shrinkage/min-sample logic and league/market priors.
- Keep backward compatibility by preserving a numeric confidence field for existing call sites.

3. Integrate prior into runtime ranking and observability
- Inject quality prior metadata into candidate payload in `scheduler.py`.
- Apply bounded ranking adjustment (or explicit gating penalty/bonus) using prior quality state.
- Log prior state and confidence provenance in reject/accept telemetry.

## Testing Implications

- Add deterministic unit tests for prior computation (quality state transitions by sample size and win-rate buckets).
- Add confidence de-bias tests ensuring low-sample team history does not dominate confidence output.
- Add scheduler integration tests validating ranking/filter payload includes quality-prior fields and remains deterministic under fixed fixtures.

## Validation Architecture

- Verify WR-05 via deterministic tests on confidence component outputs and anti-bias sample behavior.
- Verify WR-06 via scheduler/runtime tests asserting quality-prior fields influence ranking context and are observable in logs.
- Regression-check existing dry-run scheduler path to ensure no telemetry breakage.

## Discovery Level

Level 0 (existing stack and patterns only):
- No new third-party dependencies required.
- Uses existing SQLite historical records and scheduler telemetry pipeline.
