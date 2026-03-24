# v1.1 Feature Research

## Table Stakes
- League-level `rho` calibration from historical scorelines.
- Historical Brier score evaluation over reproducible samples.
- Historical win-rate and ROI diagnostics by market.
- Safe historical signal backfill into SQLite for confidence calibration.

## Differentiators
- Combined quality panel: calibration deltas + Brier + market-level ROI in one run.
- Cache-first data ingestion to minimize network dependence and rerun cost.

## Anti-Features (Out of Scope)
- Building a web dashboard in this milestone.
- Expanding into multiple new betting markets before calibration quality is stable.
- Multi-user architecture changes.

## Complexity Notes
- Team name mismatch between historical CSV and xG source is a known quality risk.
- Market odds availability is uneven across historical seasons and leagues.
- Calibration quality depends on minimum sample size per league.
