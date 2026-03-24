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

### Active

- [ ] Execute calibration pipeline with historical data cache and league-level rho output.
- [ ] Add historical diagnostics (Brier score, win-rate, ROI) as repeatable operator checks.
- [ ] Populate historical calibration data in SQLite with idempotent safeguards.

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
- Milestone v1.1 is now active with calibration/backtesting scope.
- Existing runtime safety baseline remains the quality floor for all new changes.

## Current Milestone: v1.1 Calibracao Estatistica e Backtesting Operacional

**Goal:** Improve model calibration confidence with reproducible historical evaluation and safe persistence of calibration-oriented history.

**Target features:**
- End-to-end calibration script for historical ingestion and rho-by-league output.
- Historical quality metrics (Brier and market-level win-rate/ROI) for operator feedback.
- Safe historical backfill in `sinais` with duplicate guard and source tagging.

## Next Milestone Goals

- Deliver v1.1 requirements mapped to executable phases 7-9.
- Keep reliability-first approach while extending model calibration quality checks.
- Preserve current runtime safety guarantees while introducing incremental improvements only.

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
| Prioritize calibration quality before market expansion in v1.1 | Better confidence calibration raises signal trust without adding product surface area | — Pending |

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
*Last updated: 2026-03-24 after v1.1 milestone initialization*
