---
phase: 7
slug: historical-calibration-baseline
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-24
---

# Phase 7 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python runtime checks plus script-level assertions |
| **Config file** | none |
| **Quick run command** | python calibrar_modelo.py |
| **Full suite command** | python -m unittest discover -s tests -p "test_*.py" |
| **Estimated runtime** | ~60-180 seconds |

---

## Sampling Rate

- **After every task commit:** Run python calibrar_modelo.py
- **After every plan wave:** Run python -m unittest discover -s tests -p "test_*.py"
- **Before /gsd-verify-work:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | CAL-03 | script smoke | python calibrar_modelo.py | yes | pending |
| 07-01-02 | 01 | 1 | CAL-01 | script smoke | python calibrar_modelo.py | yes | pending |
| 07-02-01 | 02 | 2 | CAL-02 | output verification | python calibrar_modelo.py | yes | pending |

*Status: pending, green, red, flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Confirm operator readability of calibration table | CAL-02 | table readability is qualitative | Run python calibrar_modelo.py and inspect printed table headings and value alignment |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] nyquist_compliant true set in frontmatter

**Approval:** pending
