# Requirements: Edge Protocol Bot

**Defined:** 2026-03-24
**Core Value:** Generate fewer but higher-confidence betting signals with disciplined risk management and measurable post-result feedback.

## v1 Requirements

### Data Reliability

- [ ] **DATA-01**: Odds collection retries transient failures with bounded backoff and clear error classification.
- [ ] **DATA-02**: Result verification tolerates partial API failure without blocking the whole cycle.
- [ ] **DATA-03**: xG/form inputs are validated before model execution, with safe fallbacks when missing.
- [ ] **DATA-04**: Daily run includes a data-health summary for key providers.

### Signal Quality

- [x] **QUAL-01**: Triple gate logic emits explicit reject reasons for every blocked signal.
- [x] **QUAL-02**: Confidence and edge thresholds are centralized and versioned for auditability.
- [x] **QUAL-03**: Stake sizing always enforces bankroll safety caps, even under malformed inputs.
- [x] **QUAL-04**: Post-result CLV/Brier metrics are consistently linked to signal IDs without orphan records.

### Operational Resilience

- [x] **OPS-01**: Scheduler jobs are idempotent for repeated/overlapping execution windows.
- [x] **OPS-02**: Per-game failures are isolated and logged without aborting the full job batch.
- [ ] **OPS-03**: Critical workflow steps emit structured logs suitable for daily diagnostics.
- [ ] **OPS-04**: Startup checks validate required env variables and database availability before running loops.

### Testing and Verification

- [ ] **TEST-01**: Core model math and gate decisions have automated tests with deterministic fixtures.
- [ ] **TEST-02**: Database write paths for signals/results are covered by integration-style tests.
- [ ] **TEST-03**: A smoke command validates end-to-end dry-run behavior without sending Telegram messages.

## v2 Requirements

### Product Expansion

- **V2-01**: Build a lightweight web monitoring interface for daily operations.
- **V2-02**: Add adaptive threshold tuning based on rolling model performance.
- **V2-03**: Introduce richer league-specific calibration profiles.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full SaaS multi-user platform | Not aligned with current single-operator scope |
| Mobile app | Low leverage compared to reliability hardening |
| New betting markets expansion | First improve quality and reliability in current markets |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Pending |
| QUAL-01 | Phase 2 | Complete |
| QUAL-02 | Phase 2 | Complete |
| QUAL-03 | Phase 2 | Complete |
| QUAL-04 | Phase 2 | Complete |
| OPS-01 | Phase 3 | Complete |
| OPS-02 | Phase 3 | Complete |
| OPS-03 | Phase 3 | Pending |
| OPS-04 | Phase 3 | Pending |
| TEST-01 | Phase 4 | Pending |
| TEST-02 | Phase 4 | Pending |
| TEST-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after initial definition*
