# Retrospective

## Milestone: v1.0 - Reliability and Signal Quality Hardening

**Shipped:** 2026-03-24
**Phases:** 6 | **Plans:** 11

### What Was Built
- Ingestion resilience with categorized retry/failure handling and provider-health observability.
- Signal quality hardening with centralized policy thresholds and explicit reject metadata.
- Operational resilience with idempotent scheduler windows, preflight fail-fast checks, and structured logs.
- Deterministic unit/integration test baseline plus safe no-send dry-run runtime flow.
- Verification-chain closure and metadata reconciliation for full milestone audit consistency.

### What Worked
- Phase-by-phase scope with executable plans kept implementation focused and reviewable.
- Strong verification artifacts (SUMMARY + VERIFICATION + UAT) reduced ambiguity in audits.
- Quick gap-closure phases (05/06) efficiently resolved governance drift without code churn.

### What Was Inefficient
- Milestone completion flow required manual follow-through after partial automation from helper CLI.
- Generated runtime artifacts (pyc/db) occasionally increased commit noise during docs-driven steps.

### Patterns Established
- Maintain explicit requirements-completed metadata in summary frontmatter.
- Always create phase-level VERIFICATION artifacts before milestone closure.
- Use dry-run and test discovery as recurring integration checkpoints.

### Key Lessons
- Process artifacts are first-class deliverables when milestone closure depends on audit integrity.
- Small focused closure phases are effective for resolving documentation/traceability gaps.

### Cost Observations
- Most cost was concentrated in iterative verification and audit/metadata reconciliation.
- Reusing existing test evidence and deterministic checks provided efficient closure confidence.

## Milestone: v1.2 - Win Rate Integrity and Runtime Quality

**Shipped:** 2026-03-25
**Phases:** 4 | **Plans:** 9

### What Was Built
- Runtime gate integrity restoration with real lineup/odd/daily-count inputs and explicit gate reject reason telemetry.
- Provider-health categorization hardening with status-aware cycle counters across timeout/http/connection/empty payload outcomes.
- Deterministic settlement resolution with fixture-id-first matching and date-safe fallback for cross-day pending signals.
- Confidence de-bias foundation and market+league quality-prior integration into runtime ranking and observability.
- No-vig market divergence in Gate 1 and expanded runtime market coverage (`1x2_fora`, `under_2.5`) with guardrails preserved.
- Reproducible local verification baseline via pinned dependencies and canonical `python scripts/run_tests.py` command.

### What Worked
- Wave-based execution (10->11->12->13) kept high-risk behavior changes isolated and verifiable.
- Regression tests were extended alongside each behavior change, preventing hidden contract drift.
- Existing summary/verification artifacts made milestone closure traceability straightforward.

### What Was Inefficient
- Milestone CLI extraction missed one-liner/task metadata, requiring manual milestone register enrichment.
- Runtime side artifacts (`.pyc`, local DB churn) increased git noise during docs-only closure steps.

### Patterns Established
- Keep gate payload contracts explicit (`odd_oponente_mercado`) when probability semantics change.
- Preserve deterministic scheduler ordering whenever ranking logic is expanded.
- Maintain one-command baseline tests as a release criterion for milestone closure.

### Key Lessons
- Probability comparison improvements (no-vig) are safest when implemented with compatibility fallback and dedicated regression tests.
- Milestone closure quality improves when archival automation is followed by manual metadata sanity checks.

### Cost Observations
- Most cost concentrated in validation hardening and reproducibility stabilization (dependency and baseline test path).
- Incremental phase scope kept execution predictable despite cross-cutting scheduler and settlement changes.

## Cross-Milestone Trends

| Trend | Status | Notes |
|-------|--------|-------|
| Verification discipline | Improving | v1.0 ended with full phase verification chain in place |
| Requirements traceability fidelity | Improving | Frontmatter + traceability mapping now aligned |
| Nyquist coverage completeness | Partial | Legacy phases still need optional validation pass |
