---
phase: 14-calibration-automation-and-league-home-advantage
status: passed
verified_on: 2026-03-24
plans_verified: [14-01, 14-02]
---

# Phase 14 Verification

## Commands

- python -m unittest tests.test_poisson_calibracao_runtime -v
- python -m unittest tests.test_poisson_over_under_dc -v

## Result

- All targeted phase-14 regression suites passed.
- CAL-01, CAL-02, and CAL-03 behaviors were validated through automated tests.

## Notes

- Calibration runtime file bootstrap created at `data/calibracao_ligas.json`.
- Existing call signatures remain compatible while new optional parameters were introduced.
