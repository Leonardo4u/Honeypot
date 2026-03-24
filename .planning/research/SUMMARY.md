# v1.1 Research Summary

## Scope
Milestone v1.1 focuses on model calibration and historical backtesting operations.

## Stack Additions
- Add or standardize `pandas` and `requests` for robust historical data ingestion.
- Reuse existing `numpy`, `scipy`, `sqlite3`, and project model modules.

## Feature Table Stakes
- League-level rho calibration.
- Historical Brier score and market win-rate/ROI diagnostics.
- Idempotent historical backfill into `sinais` with source tagging.

## Key Architecture Direction
- Keep script-first architecture.
- Introduce calibration flow as an operational script integrated with existing model/data modules.
- Preserve existing scheduler/runtime behavior; v1.1 is additive and low-risk.

## Watch Out For
- Team-name mapping drift between sources.
- Sparse samples per league leading to noisy calibration.
- Duplicate backfill records and odds-quality inconsistencies.

## Recommended Milestone Shape
- Phase 7: Historical data and calibration baseline.
- Phase 8: Diagnostics quality (Brier/win-rate/ROI confidence).
- Phase 9: Historical persistence hardening and operator workflow.
