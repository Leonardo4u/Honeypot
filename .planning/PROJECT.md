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

### Active

- [ ] Increase reliability of external data ingestion (odds/results/xG) with better retries, fallbacks, and observability.
- [ ] Improve signal quality controls to reduce noisy picks and improve consistency of edge decisions.
- [ ] Strengthen operational safety (idempotency, failure isolation, and monitoring) for long-running scheduler execution.
- [ ] Formalize validation and test coverage for critical business logic.

### Out of Scope

- Full web dashboard with custom frontend UI — current scope prioritizes backend reliability and signal quality.
- Multi-tenant SaaS architecture — current project remains single-operator and locally orchestrated.

## Context

- Stack is Python script-first with `scheduler.py` as orchestration center.
- Signal analysis uses Poisson/edge models in `model/` and integration/persistence modules in `data/`.
- Runtime uses local files + SQLite + Telegram + external APIs.
- Codebase map already exists in `.planning/codebase/` and should be treated as architectural reference.

## Constraints

- **Execution Model**: Long-running scheduler on Windows environment — must remain robust to transient API/network failures.
- **Data Sources**: Multiple external APIs and scraping paths — response instability is expected and must be handled.
- **Operational Simplicity**: Single-operator workflow — changes should preserve straightforward run/debug process.
- **Risk Control**: Bankroll and stake sizing are core safeguards — regressions here are high-impact.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep script-oriented architecture for now | Fast iteration and existing operational familiarity | — Pending |
| Prioritize reliability and validation before adding new product surfaces | Better signal trustworthiness gives highest immediate value | — Pending |
| Use phased hardening approach (data reliability -> model gates -> ops quality) | Reduces risk and keeps changes reviewable | — Pending |

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
*Last updated: 2026-03-24 after initialization*
