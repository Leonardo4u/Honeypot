---
phase: 03
slug: operational-resilience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 03 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | compile-and-assert commands (pytest deferred to phase 4) |
| **Config file** | none - Wave 0 installs in phase 4 |
| **Quick run command** | `python -m py_compile scheduler.py data/database.py` |
| **Full suite command** | `python -m py_compile scheduler.py data/database.py data/ingestion_resilience.py` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m py_compile scheduler.py data/database.py`
- **After every plan wave:** Run `python -m py_compile scheduler.py data/database.py data/ingestion_resilience.py`
- **Before /gsd-verify-work:** Full compile sweep for changed phase files
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | OPS-01 | static/compile | `python -m py_compile data/database.py scheduler.py` | yes | pending |
| 03-01-02 | 01 | 1 | OPS-02 | static/assert | `python -m py_compile scheduler.py` | yes | pending |
| 03-02-01 | 02 | 2 | OPS-04 | static/assert | `python -m py_compile scheduler.py data/database.py` | yes | pending |
| 03-02-02 | 02 | 2 | OPS-03 | static/assert | `python -m py_compile scheduler.py` | yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase3_resilience.py` - deterministic guard/preflight tests (deferred to Phase 4 test baseline)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Preflight fail-fast with missing env | OPS-04 | Requires controlled env toggles | Run scheduler with BOT_TOKEN unset and confirm explicit abort message |
| Duplicate window skip path | OPS-01 | Needs repeated trigger simulation | Invoke guarded job twice in same window and confirm second run logs idempotent skip |

---

## Validation Sign-Off

- [x] All tasks have automated verify commands in PLAN
- [x] Sampling continuity defined
- [x] Wave 0 gap recorded
- [x] No watch-mode flags
- [x] Feedback latency target set
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
