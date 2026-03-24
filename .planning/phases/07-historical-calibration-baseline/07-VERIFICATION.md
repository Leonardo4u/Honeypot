# Verification: Phase 07 - Historical Calibration Baseline

**Date:** 2026-03-24  
**Status:** passed

## Goal Check

Goal: Establish a reliable calibration pipeline that ingests historical data and estimates per-league rho values.

## Must-Haves Validation

### Truths

- Operator can run one command and the script starts a full calibration cycle: **PASS**
- Historical CSV files are reused from cache when already present: **PASS**
- Script does not stop entire run because of single-row or single-match failures: **PASS**
- Calibration run prints rho values by league with baseline comparison: **PASS**
- Run output clearly tells how to apply calibrated rho values manually: **PASS**

### Artifacts

- calibrar_modelo.py: **PASS**
- .planning/phases/07-historical-calibration-baseline/07-01-SUMMARY.md: **PASS**
- .planning/phases/07-historical-calibration-baseline/07-02-SUMMARY.md: **PASS**

### Key Link Spot Checks

- cache-first branch exists before HTTP download (`os.path.exists(path)` and `[CACHE]` output): **PASS**
- calibration report imports `estimar_rho` and `RHO_POR_LIGA` from `poisson`: **PASS**
- league calibration table includes Liga/Atual/Calibrado/Delta/N jogos: **PASS**
- final guidance explicitly states manual update of `RHO_POR_LIGA` in `poisson.py`: **PASS**

## Automated Checks

- python -m py_compile calibrar_modelo.py: pass
- python calibrar_modelo.py: pass

## Requirement Coverage

- CAL-01: **PASS** (single command executes full calibration cycle)
- CAL-02: **PASS** (per-league rho baseline-vs-calibrated output with sample size)
- CAL-03: **PASS** (cache-aware historical loading without re-download)

## Notes

- Runtime warnings from pandas date parsing/fragmentation were non-blocking and did not prevent successful execution.
- Historical runtime produced local artifacts under `data/historico/` and updated `data/edge_protocol.db` as expected from script behavior.

---
*Generated after execute-phase equivalent run*
