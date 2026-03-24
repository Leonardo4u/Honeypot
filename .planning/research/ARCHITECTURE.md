# v1.1 Architecture Research

## Integration Points
- Data ingestion entrypoint: new root script `calibrar_modelo.py`.
- Model calibration source: `model/poisson.py` (`estimar_rho`, probability functions).
- xG feature source: `data/xg_understat.py` (`calcular_media_gols_com_xg`).
- Persistence target: `data/edge_protocol.db`, table `sinais`.

## New vs Modified Components
- New component: calibration/backtesting runner script.
- Existing components reused (no required refactor in milestone bootstrap):
  - `model/poisson.py`
  - `data/xg_understat.py`
  - `data/database.py` schema assumptions

## Data Flow (v1.1)
1. Download or reuse cached league CSV history.
2. Normalize fields to internal naming contract.
3. Estimate per-league `rho` from historical goals.
4. Compute historical Brier and market diagnostics using current model pipeline.
5. Optionally backfill historical synthetic signals with `fonte='historico'`.
6. Use these records in confidence calibration paths.

## Build Order Recommendation
1. Calibration script and deterministic loading pipeline.
2. Metrics and diagnostics (Brier/win-rate/ROI).
3. Historical backfill safety and duplicate guard.
4. Milestone verification and threshold update policy.
