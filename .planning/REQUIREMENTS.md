# Requirements: Edge Protocol Bot

**Defined:** 2026-03-24
**Milestone:** v1.3 Calibration Freshness and Portfolio Risk Controls
**Core Value:** Generate fewer but higher-confidence betting signals with disciplined risk management and measurable post-result feedback.

## v1 Requirements

### Calibration Automation and Model Consistency

- [x] **CAL-01**: Dixon-Coles rho per league must be applied automatically in runtime after calibration updates (no manual parameter sync).
- [x] **CAL-02**: Poisson must support league-specific home-advantage factor in lambda_home calculation.
- [x] **CAL-03**: Over/under probabilities must include Dixon-Coles low-score correction to stay consistent with 1x2 behavior.

### Freshness and Confidence Quality

- [x] **XGF-01**: xG aggregation must use temporal decay weighting so recent matches influence predictions more than older matches.
- [x] **CONF-01**: Confidence fallback for prior state `sem_sinal` must use proxy quality signals (league stability, scoring profile, or volatility) instead of only floor behavior.
- [x] **MODEL-01**: SOS adjustment cap must be more conservative when based on fallback averages instead of trusted xG inputs.

### Gate and Market Signal Robustness

- [x] **GATE-01**: Motivation gate standings data must use persistent cache between scheduler cycles/restarts with controlled TTL.
- [x] **GATE-02**: No-vig normalization must validate source quality (sharp/liquid bookmaker source) before applying opponent-odd normalization.
- [x] **GATE-03**: Divergence gate must compare base Poisson probability (pre-contextual adjustment) against market implied probability.
- [x] **STEAM-01**: Steam bonus must require minimum elapsed market-open window before bonus can be applied.

### Portfolio Correlation Risk

- [ ] **RISK-01**: Candidate ranking must enforce per-match market cap to avoid multiple highly correlated picks from the same fixture.
- [ ] **RISK-02**: Kelly sizing must apply additional stake reduction when open signals are same-match correlated.

### Operational Quality Telemetry

- [ ] **OBS-01**: A weekly job must compute and persist Brier/win-rate trend metrics from real settled `sinais` data.
- [ ] **SETTLE-01**: Settlement lookup window must be configurable by competition profile (including wider windows for European competitions).
- [ ] **OBS-02**: Drift detection must send Telegram alert when quality metrics exceed configured degradation thresholds over time.

## v2 Requirements

### Future Expansion

- **EXP-01**: Online threshold tuner for market/league priors with walk-forward validation.
- **EXP-02**: Automated strategy simulation for correlated portfolio stress scenarios.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend dashboard redesign | v1.3 focus is model/risk quality and operational safeguards |
| New Telegram UX commands | Scope is signal quality internals, not bot interaction surface |
| Multi-tenant operation model | Single-operator workflow remains the target runtime |

## Traceability

| Requirement | Planned Phase | Status |
|-------------|---------------|--------|
| CAL-01 | Phase 14 | Completed |
| CAL-02 | Phase 14 | Completed |
| CAL-03 | Phase 14 | Completed |
| XGF-01 | Phase 15 | Completed |
| CONF-01 | Phase 15 | Completed |
| MODEL-01 | Phase 15 | Completed |
| GATE-01 | Phase 16 | Completed |
| GATE-02 | Phase 16 | Completed |
| GATE-03 | Phase 16 | Completed |
| STEAM-01 | Phase 16 | Completed |
| RISK-01 | Phase 17 | Pending |
| RISK-02 | Phase 17 | Pending |
| OBS-01 | Phase 18 | Pending |
| SETTLE-01 | Phase 18 | Pending |
| OBS-02 | Phase 18 | Pending |

**Coverage:**
- v1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after phase 15 execution completion*
