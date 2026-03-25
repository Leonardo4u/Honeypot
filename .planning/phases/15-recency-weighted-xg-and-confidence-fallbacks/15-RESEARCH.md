---
phase: 15-recency-weighted-xg-and-confidence-fallbacks
date: 2026-03-24
focus: XGF-01 CONF-01 MODEL-01
---

# Phase 15 Research

## Current Reality
- `data/xg_understat.py` computes team xG means with equal weight across all historical matches in the season.
- `data/forma_recente.py` confidence path (`calcular_confianca_contexto`) clamps at 50 when prior is weak/absent and lacks extra fallback proxies.
- `data/sos_ajuste.py` applies broad SOS clamp range (`0.7..1.5`) regardless of data quality source (`xG` vs fallback medias).

## Risks
- Equal weighting in xG may underreact to recent form shifts.
- Hard floor-only confidence behavior on `sem_sinal` can over-penalize new league/market combinations.
- Aggressive SOS scaling on fallback medias can amplify noise.

## Recommended Direction
1. Add exponential time decay in xG aggregation with deterministic defaults (e.g., decay base 0.9) and keep backward-compatible outputs.
2. Enrich confidence fallback path for `sem_sinal` using low-risk proxies (sample coverage, media availability, team-history size) while preserving 50..100 bounds.
3. Make SOS clamp adaptive by source quality: conservative range for fallback medias, wider range for trusted xG.

## Verification Targets
- Unit tests for decay weighting behavior and deterministic output shape in xG pipeline.
- Confidence tests validating `sem_sinal` proxy uplift remains bounded and explainable.
- SOS tests asserting conservative cap under fallback source and legacy cap under xG source.
