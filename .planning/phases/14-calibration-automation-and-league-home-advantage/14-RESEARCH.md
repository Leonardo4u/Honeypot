---
phase: 14-calibration-automation-and-league-home-advantage
date: 2026-03-24
focus: CAL-01 CAL-02 CAL-03
---

# Phase 14 Research

## Context
- `model/poisson.py` already supports Dixon-Coles for 1x2 and league rho lookup via static `RHO_POR_LIGA`.
- `calibrar_modelo.py` computes `rho_calibrado` per league but only prints values for manual copy/paste.
- `calcular_prob_over_under` still uses pure Poisson without `tau`, creating inconsistency with 1x2 correction.

## Recommended Direction
1. Persist calibration outputs to versioned runtime file (`data/calibracao_ligas.json`) containing `rho` and optional `home_advantage` by league.
2. Load persisted calibration at runtime in `poisson.py` with robust fallback to `RHO_POR_LIGA` and `RHO_DEFAULT`.
3. Add league home-advantage multiplier support in lambda_home path, keeping behavior unchanged when league data is absent.
4. Reuse a shared Dixon-Coles matrix builder for both 1x2 and over/under calculations to guarantee probability consistency.

## Risks
- Missing/invalid calibration file must not break scheduler runtime.
- Over/under DC correction can shift historical thresholds; tests should assert normalization and expected directional behavior.

## Verification Targets
- Unit tests for calibration file load precedence and fallback behavior.
- Unit tests for league-specific home-advantage effect on `prob_casa` monotonicity.
- Unit tests for DC-corrected over/under normalization and low-score sensitivity.
