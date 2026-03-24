# v1.1 Stack Research

## Scope
New capabilities for calibration and historical backtesting in the existing Python bot.

## Recommended Additions
- `pandas` for CSV ingestion, normalization, and sampling.
- `requests` for historical CSV download with timeout/retry-safe behavior.
- Keep `numpy` and `scipy` as existing statistical core.

## Keep As-Is
- SQLite (`sqlite3`) as single-operator persistence layer.
- Script-first execution model (`python <script>.py`).
- Existing Poisson and xG modules as source-of-truth for probability generation.

## Integration Notes
- Calibration script should run from project root and resolve modules via path setup.
- Historical CSVs should be cached under `data/historico/` and reused in next runs.
- Backfill into `sinais` table must be idempotent (`fonte='historico'` guard).

## Avoid
- New orchestration framework.
- New database engine.
- Real-time services for this milestone.
