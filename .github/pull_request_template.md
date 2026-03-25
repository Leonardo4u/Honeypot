## Summary
- [ ] Describe what changed and why.

## Validation
- [ ] `python scripts/run_tests.py`
- [ ] `python scripts/check_repo_hygiene.py`
- [ ] `python scripts/smoke_test.py`

## Release Checklist (mandatory)
- [ ] Promotion gate passed: `python scripts/check_promotion_gate.py`
- [ ] No generated artifacts tracked (`.pyc`, `.db`, `logs/*.xlsx`)
- [ ] Runbook impact reviewed (`docs/runbooks/*`)
- [ ] Incident checklist impact reviewed (`docs/security/incident-checklist.md`)
- [ ] Env vars documented in README if changed

## Risk and Rollback
- [ ] Rollback path explained
- [ ] Operational risk assessed (provider, settlement, alerting)
