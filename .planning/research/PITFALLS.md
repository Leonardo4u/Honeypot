# v1.1 Pitfalls Research

## High-Risk Pitfalls
- Team-name mismatch across data providers causes fallback overuse and biased metrics.
- Using sparse league samples produces unstable `rho` calibration.
- Backfill duplication pollutes confidence calibration and ROI interpretation.
- Overinterpreting historical ROI from mixed odds quality or missing columns.

## Prevention Strategy
- Track and report `% sem xG` for every run.
- Enforce minimum sample checks before accepting calibrated `rho`.
- Hard guard duplicate inserts using `fonte='historico'` count checks.
- Log selected odd source and skip invalid/low-quality odds rows.

## Where To Address
- Data quality and normalization: early milestone phase.
- Calibration and diagnostics robustness: middle phase.
- Persistence and operational safety checks: final phase.
