# Edge Protocol Bot

## What This Is

A Python automation bot that analyzes football matches, estimates probabilities, filters value bets, and publishes qualified signals to Telegram channels. It also tracks post-bet quality metrics (CLV and Brier), updates bankroll state, and produces operational reports. The target user is a solo operator who needs consistent, repeatable daily betting operations with clear risk controls.

## Core Value

Generate fewer but higher-confidence betting signals with disciplined risk management and measurable post-result feedback.

## Requirements

### Validated

- ✓ Daily scheduled signal generation and result verification loops are running from `scheduler.py`.
- ✓ Telegram delivery and command-based bot interactions are available via `scheduler.py` and `bot/telegram_bot.py`.
- ✓ Persistent storage and historical tracking are implemented with SQLite in `data/database.py`.
- ✓ Signal-quality controls were hardened with centralized thresholds, structured reject reasons, and safer stake/linkage handling (validated in Phase 2: Signal Quality Controls).
- ✓ Data ingestion resilience and provider-health observability were hardened with retry categorization and validation/fallback controls (validated in Phases 1 and 6 reconciliation).
- ✓ Operational resilience baseline (idempotent scheduler windows, startup preflight, structured diagnostics) is verified and stable (validated in Phase 3).
- ✓ Deterministic model/gate tests, DB integration tests, and dry-run no-send runtime checks are established and verified (validated in Phases 4 and 5).
- ✓ Historical calibration baseline is operational with cache-aware ingestion and league-level rho reporting (validated in Phase 7: Historical Calibration Baseline).
- ✓ Settlement labeling is deterministic across pending days with fixture identity persistence and date-safe fallback resolution (validated in Phase 11: Settlement Label Integrity).
- ✓ Confidence scoring is de-biased with sample-aware market+league quality prior and runtime observability (validated in Phase 12: Confidence De-bias and Quality Prior).
- ✓ Market divergence uses no-vig comparison, runtime market coverage was expanded, and reproducible one-command test baseline is established (validated in Phase 13: No-vig Comparison, Market Coverage, and Test Baseline).
- ✓ Runtime calibration now auto-applies league rho/home-advantage and over/under uses Dixon-Coles consistency with dedicated regressions (validated in Phase 14: Calibration Automation and League Home Advantage).
- ✓ xG now uses recency-weighted decay, confidence sem_sinal uses bounded proxy fallback, and SOS caps adapt to source quality (validated in Phase 15: Recency-Weighted xG and Confidence Fallbacks).
- ✓ Gate robustness now includes persistent standings cache, source-aware no-vig/divergence baseline checks, steam maturity window, per-match ranking cap, and minimal drift/fallback telemetry alerts (validated in Phase 16: Gate Robustness and Steam Noise Filtering).
- ✓ Portfolio concentration control now includes correlation-aware ranking penalty and same-match Kelly stake reducer with runtime propagation from scheduler (validated in Phase 17: Correlation-Aware Portfolio Controls).

### Active

- [ ] Add weekly quality telemetry with segmented historical trend persistence for Brier/win-rate quality signals.
- [ ] Make settlement lookup windows configurable by competition profile to reduce unresolved pendentes.
- [ ] Expand drift safeguards with durable thresholded alerts over longer rolling horizons.

### Out of Scope

- Full web dashboard with custom frontend UI — current scope prioritizes backend reliability and signal quality.
- Multi-tenant SaaS architecture — current project remains single-operator and locally orchestrated.

## Context

- Stack is Python script-first with `scheduler.py` as orchestration center.
- Signal analysis uses Poisson/edge models in `model/` and integration/persistence modules in `data/`.
- Runtime uses local files + SQLite + Telegram + external APIs.
- Codebase map already exists in `.planning/codebase/` and should be treated as architectural reference.

## Current State

- Milestone v1.0 (Reliability and Signal Quality Hardening) is shipped and archived.
- Milestone v1.1 (Calibracao Estatistica e Backtesting Operacional) is shipped and archived.
- Milestone v1.2 (Win Rate Integrity and Runtime Quality) is shipped and archived.
- Existing runtime safety baseline remains the quality floor for all new changes.
- Milestone v1.3 is active for model calibration and portfolio risk controls.

## Current Milestone: v1.3 Calibration Freshness and Portfolio Risk Controls

**Goal:** Improve signal quality consistency by making calibration outputs operational, reducing stale priors, and controlling portfolio correlation risk.

**Target features:**
- Add automated weekly quality telemetry and segmented history retention for trend diagnosis.
- Configure settlement lookup windows by competition profile (including European competitions).
- Expand drift alerting for longer-horizon degradation detection and operator notification.

## Last Shipped Milestone: v1.2 Win Rate Integrity and Runtime Quality

**Goal achieved:** Increase win-rate reliability with deterministic settlement, restored gate integrity, no-vig divergence checks, and prior-aware runtime selection.

**Delivered features:**
- Runtime gate payloads now consume real lineup/odd/daily-count context with explicit reject telemetry.
- Provider health counters now classify timeout/http/connection/empty payload status paths consistently.
- Settlement resolution is fixture-id-first with date-safe fallback for cross-day pending bets.
- Confidence context includes market+league quality priors and deterministic prior-aware scheduler ranking.
- Gate 1 compares model divergence against no-vig market probability when both market sides exist.
- Reproducible test baseline established with pinned dependencies and canonical command `python scripts/run_tests.py`.

## Previous Shipped Milestone: v1.1 Calibracao Estatistica e Backtesting Operacional

**Goal achieved:** Improve model calibration confidence with reproducible historical evaluation and safe persistence of calibration-oriented history.

**Delivered features:**
- End-to-end calibration script for historical ingestion and rho-by-league output.
- Historical quality metrics (Brier and market-level win-rate/ROI) for operator feedback.
- Safe historical backfill in `sinais` with duplicate guard and source tagging.

## Next Milestone Goals

- Deliver phased implementation of calibration freshness, gate hardening, and portfolio-risk controls.
- Keep v1.2 verification baseline as mandatory non-regression floor.
- Add observability loops that detect degradation before bankroll impact compounds.

## Constraints

- **Execution Model**: Long-running scheduler on Windows environment — must remain robust to transient API/network failures.
- **Data Sources**: Multiple external APIs and scraping paths — response instability is expected and must be handled.
- **Operational Simplicity**: Single-operator workflow — changes should preserve straightforward run/debug process.
- **Risk Control**: Bankroll and stake sizing are core safeguards — regressions here are high-impact.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep script-oriented architecture for now | Fast iteration and existing operational familiarity | ✓ Confirmed in v1.0 |
| Prioritize reliability and validation before adding new product surfaces | Better signal trustworthiness gives highest immediate value | ✓ Confirmed in v1.0 |
| Use phased hardening approach (data reliability -> model gates -> ops quality) | Reduces risk and keeps changes reviewable | ✓ Confirmed in v1.0 |
| Prioritize calibration quality before market expansion in v1.1 | Better confidence calibration raises signal trust without adding product surface area | ✓ Confirmed in v1.1 |
| Prioritize label integrity and effective gating in v1.2 | Win-rate improvement depends on clean feedback loop and strict pre-trade quality filters | ✓ Confirmed in v1.2 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after phase 17 completion*
