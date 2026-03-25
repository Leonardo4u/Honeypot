---
phase: 17-correlation-aware-portfolio-controls
status: passed
verified_on: 2026-03-25
plans_verified: [17-01, 17-02]
---

# Phase 17 Verification

## Commands

- python -m unittest tests.test_scheduler_quality_prior_ranking -v
- python -m unittest tests.test_kelly_banca_correlation -v
- python scripts/run_tests.py

## Result

- All phase-17 verification commands passed.
- Correlation-aware ranking penalty and parameterized concentration cap validated.
- Same-match Kelly reduction and scheduler context propagation validated.
- Baseline suite passed with 53 tests.

## Notes

- Ranking now applies progressive same-match penalty (`CORRELACAO_PENALTY_STEP`) prior to per-match cap selection.
- Kelly payload now includes `fator_correlacao_mesmo_jogo` to make stake-reduction provenance explicit.
