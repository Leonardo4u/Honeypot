# Requirements: Edge Protocol Bot

**Defined:** 2026-03-24
**Core Value:** Generate fewer but higher-confidence betting signals with disciplined risk management and measurable post-result feedback.

## v1 Requirements

### Calibration Pipeline

- [x] **CAL-01**: Operator can run one command to execute end-to-end historical calibration flow.
- [x] **CAL-02**: Model reports calibrated `rho` by league with baseline-vs-calibrated delta and sample size.
- [x] **CAL-03**: Historical dataset loading is cache-aware and does not redownload existing CSV files.

### Historical Evaluation

- [x] **EVAL-01**: Model computes historical Brier score over reproducible random sample.
- [x] **EVAL-02**: Evaluation reports `% without xG` fallback usage to expose data quality.
- [x] **EVAL-03**: Model reports historical win-rate and ROI by core markets with clear signal counts.

### Historical Persistence and Safety

- [x] **HIST-01**: Historical backfill inserts tagged records into `sinais` with `fonte='historico'`.
- [x] **HIST-02**: Backfill process is idempotent and skips insertion when historical records already exist.
- [x] **HIST-03**: Backfill tolerates row-level failures and continues processing remaining matches.

## v2 Requirements

### Future Expansion

- **EXP-01**: Add automatic team-name mapping reconciliation between providers.
- **EXP-02**: Add league-specific calibration acceptance thresholds and alerts.
- **EXP-03**: Add reporting export for calibration trend snapshots.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full web dashboard for calibration analytics | Keep milestone focused on model quality and operational script flow |
| New real-time streaming data pipeline | Existing batch model is sufficient for calibration cycle |
| Multi-user SaaS controls and permissions | Project remains single-operator for this milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CAL-01 | Phase 7 | Complete |
| CAL-02 | Phase 7 | Complete |
| CAL-03 | Phase 7 | Complete |
| EVAL-01 | Phase 8 | Complete |
| EVAL-02 | Phase 8 | Complete |
| EVAL-03 | Phase 8 | Complete |
| HIST-01 | Phase 9 | Complete |
| HIST-02 | Phase 9 | Complete |
| HIST-03 | Phase 9 | Complete |

**Coverage:**
- v1 requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after phase 09 execution*
