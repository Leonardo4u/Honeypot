# Requirements: Edge Protocol Bot

**Defined:** 2026-03-24
**Milestone:** v1.2 Win Rate Integrity and Runtime Quality
**Core Value:** Increase win-rate reliability with clean outcome labeling, effective pre-trade gates, and market-quality-aware selection.

## v1 Requirements

### Runtime Gate Integrity

- [x] **WR-01**: Gate inputs in runtime must use real lineup, odd variation, and daily-limit context (no fixed placeholders).
- [x] **WR-02**: Gate 4 must enforce real daily-count constraints and expose explicit reason codes in logs.

### Settlement Label Integrity

- [x] **WR-03**: Result settlement must match fixtures deterministically (fixture id and/or date-safe fallback) to avoid wrong game closure.
- [x] **WR-04**: Settlement must avoid day-only lookup assumptions and support pending bets from previous days.

### Confidence and Selection Quality

- [x] **WR-05**: Confidence calculation must reduce selection bias from self-selected bet history and use explicit quality priors.
- [x] **WR-06**: Runtime ranking/filtering must include historical market+league quality prior (minimum sample + quality state).

### Market Probability and Coverage

- [ ] **WR-07**: Model-vs-market divergence must use no-vig market probability rather than raw 1/odd.
- [ ] **WR-08**: Runtime market coverage must expand beyond current pair with guardrails focused on hit-rate quality.

### Operational Reliability for Iteration

- [x] **WR-09**: Provider-health counters must categorize timeout/http/connection/empty payload consistently in cycle telemetry.
- [ ] **WR-10**: Test baseline must be reproducible with pinned dependencies and a single local test command.

## v2 Requirements

### Future Expansion

- **EXP-01**: Add online threshold tuner for market/league priors with walk-forward validation.
- **EXP-02**: Add confidence calibration report per league with drift alerts.
- **EXP-03**: Add automated rollback switch for degraded provider health windows.

## Out of Scope

| Feature | Reason |
|---------|--------|
| New Telegram UX features | Milestone focus is win-rate integrity, not product surface expansion |
| Dashboard rewrite | Existing reporting path is sufficient for this quality-hardening cycle |
| Multi-tenant execution | Single-operator runtime remains the intended operating model |

## Traceability

| Requirement | Planned Phase | Status |
|-------------|---------------|--------|
| WR-01 | Phase 10 | Completed |
| WR-02 | Phase 10 | Completed |
| WR-03 | Phase 11 | Completed |
| WR-04 | Phase 11 | Completed |
| WR-05 | Phase 12 | Completed |
| WR-06 | Phase 12 | Completed |
| WR-07 | Phase 13 | Planned |
| WR-08 | Phase 13 | Planned |
| WR-09 | Phase 10 | Completed |
| WR-10 | Phase 13 | Planned |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-25 after phase 12 execution completion*
