---
phase: 07
name: Historical Calibration Baseline
status: complete
generated: 2026-03-24
source: plan-phase
---

# Phase 07 Research

## Scope
Implement a reliable historical calibration baseline that can run from a single command and reuse cached CSV data.

## Existing Assets
- Existing model calibration functions exist in model/poisson.py (estimar_rho, calcular_probabilidades).
- Existing xG fallback flow exists in data/xg_understat.py via calcular_media_gols_com_xg.
- SQLite persistence exists in data/edge_protocol.db and table sinais.
- New script calibrar_modelo.py already created at project root and should be treated as the central operator entrypoint.

## Implementation Guidance
- Keep script-first architecture and avoid scheduler coupling in this phase.
- Use deterministic sampling or deterministic ordering for repeatable outputs where possible.
- Keep per-row processing fault-tolerant (continue on row-level errors).
- Ensure historical cache folder structure is stable: data/historico/<liga>/<temporada>.csv.

## Risks and Mitigations
- Team naming mismatches between historical CSV and local xG map can reduce xG coverage:
  - Mitigation: report fallback usage and maintain transparent counters.
- Incomplete odds columns in older seasons can skew diagnostics:
  - Mitigation: explicit odds validation and conservative fallback handling.
- Duplicate historical backfill can contaminate confidence metrics:
  - Mitigation: strict fonte='historico' guard before insertion.

## Validation Architecture
- Quick run: python calibrar_modelo.py
- Fast smoke should verify:
  - cached files are reused without redownload,
  - rho calibration summary is produced per league,
  - no crash on row-level malformed records.
- Data-layer checks should verify database schema assumptions before insert.

## Outputs for Planning
- Plans should produce 2 executable PLAN.md files aligned to roadmap:
  - 07-01 for ingestion/caching + normalized loading.
  - 07-02 for rho calibration reporting and operator summary.
- Every task must include automated verification commands and explicit acceptance criteria.
