# Research Summary

**Date:** 2026-03-24
**Scope:** Brownfield initialization based on mapped architecture and stack

## Key Findings

- Runtime is scheduler-centric and script-oriented, with critical orchestration in `scheduler.py`.
- Reliability risk concentrates in external data dependencies (`data/coletar_odds.py`, `data/verificar_resultados.py`, `data/xg_understat.py`).
- Signal quality controls exist but are distributed across model and scheduler constants.
- Persistence is SQLite-based and suitable for current single-operator workflow.

## Practical Priorities

1. Harden API/retry/fallback behavior before expanding features.
2. Centralize and audit quality thresholds and gate outcomes.
3. Add safety-first operational checks and deterministic tests.

## Recommended Initial Focus

Phase 1 should prioritize ingestion resilience and visibility so downstream scoring can rely on stable inputs.

---
*Generated during new-project initialization*
