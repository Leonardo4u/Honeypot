---
phase: 13-no-vig-comparison-market-coverage-and-test-baseline
date: 2026-03-25
scope: [WR-07, WR-08, WR-10]
status: complete
---

# Phase 13 Research

## Objective

Plan implementation for:
- WR-07: model-vs-market divergence must use no-vig market probability.
- WR-08: runtime market coverage expansion beyond current pair with hit-rate guardrails.
- WR-10: reproducible local test baseline with pinned dependencies and a single command.

## Current Code Findings

1. Divergence still uses raw implied probability with vig:
- `model/filtros.py` computes `divergencia = prob_modelo - (1 / odd)`.
- This is the exact hotspot for WR-07.

2. Runtime market coverage is restricted:
- `scheduler.py` iterates only `("1x2_casa", "casa")` and `("over_2.5", "over_2.5")`.
- `data/coletar_odds.py` already extracts more price points (`fora`, `under_2.5`) but runtime does not use them.

3. Signal/model capability exists for more markets:
- `model/analisar_jogo.py` supports `1x2_fora`, `under_2.5`, `btts_sim` in probability selection.
- `model/filtros.py` has EV minima map for broader markets, including `under_2.5` and `1x2_fora`.

4. Reproducible baseline is missing:
- No pinned `requirements.txt` or lockfile in repository root.
- Test suite uses `unittest`, but there is no single canonical command documented/executable wrapper.

## Recommended Technical Direction

### WR-07 (No-vig)

- Add a helper in `model/filtros.py` for no-vig normalization from 2-way market odds:
  - `prob_bruta_a = 1/odd_a`
  - `prob_bruta_b = 1/odd_b`
  - `soma = prob_bruta_a + prob_bruta_b`
  - `prob_no_vig_a = prob_bruta_a / soma`
- Pass market-opposite odd into gate payload (`odd_oponente_mercado`) from runtime where available.
- Use no-vig divergence when both sides exist; fallback to old logic only when unavailable.

### WR-08 (Market expansion)

- Expand runtime market iteration in `scheduler.py` to include `1x2_fora` and `under_2.5` first (lower integration risk, already partially supported).
- Keep guardrails:
  - preserve `MIN_EDGE_SCORE` and `MIN_CONFIANCA`.
  - keep gate chain untouched except WR-07 no-vig enhancement.
  - preserve deterministic ranking order.
- Update human-readable market labels for Telegram output.

### WR-10 (Reproducible tests)

- Add pinned `requirements.txt` (minimum tested set used by runtime/tests).
- Add one canonical test command via script (`scripts/run_tests.py`) or documented command wrapper.
- Ensure command includes current deterministic suites and new phase 13 suites.

## Risks and Mitigations

- Risk: no-vig cannot be computed for one-sided odds payloads.
  - Mitigation: keep explicit fallback path and telemetry field indicating fallback.

- Risk: adding markets increases candidate volume and may impact selection behavior.
  - Mitigation: rely on existing gate thresholds + deterministic ranking; validate with dedicated scheduler tests.

- Risk: dependency pinning could conflict with local environment.
  - Mitigation: pin only required packages already in use and validate via test command.

## Files Likely Impacted

- `model/filtros.py`
- `scheduler.py`
- `data/coletar_odds.py` (if market opposite mapping extraction needs extension)
- `model/signal_policy.py` (if EV minima map must be expanded centrally)
- `tests/test_filtros_gate.py`
- `tests/test_scheduler_quality_prior_ranking.py` and/or new scheduler market-coverage tests
- `requirements.txt` (new)
- `scripts/run_tests.py` (new) and/or docs reference

## Verification Commands (candidate)

- `python -m unittest tests.test_filtros_gate -v`
- `python -m unittest tests.test_scheduler_quality_prior_ranking -v`
- `python -m unittest discover -s tests -p "test_*.py" -v`

## Recommendation

Use 3 execute plans:
1. WR-07 no-vig gate divergence contract + tests.
2. WR-08 runtime market coverage expansion + scheduler tests.
3. WR-10 reproducible pinned dependencies + single test command baseline.
