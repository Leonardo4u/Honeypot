# Phase 3: Operational Resilience - Research

**Researched:** 2026-03-24
**Domain:** Scheduler idempotency, failure isolation, structured diagnostics, and startup preflight
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01..D-03: Idempotency by stable execution window key persisted in SQLite
- D-04..D-06: Per-fixture isolation, explicit degraded-cycle behavior for critical persistence failures
- D-07..D-08: Structured operational logs with stable fields and mandatory cycle milestones
- D-09..D-11: Fail-fast startup preflight for critical env/db/schema requirements

### the agent's Discretion
- Concrete SQLite representation for idempotency state
- Exact structured log field set and helper format

### Deferred Ideas (OUT OF SCOPE)
- Multi-worker architecture split
- New product features unrelated to operational resilience
</user_constraints>

<research_summary>
## Summary

Current runtime in scheduler.py centralizes analysis, settlement, CLV/steam monitoring, and reporting in a long-lived loop with print-based logs and broad exception handling. This makes day-to-day operation resilient in some spots but weak on deterministic idempotency and explicit startup readiness gates.

Best implementation path for Phase 3:
1. Add persistent scheduler execution control in SQLite (idempotency key + status + timestamps + reason)
2. Wrap each scheduled job invocation with a guard that performs start/skip/end logging and prevents duplicate overlapping windows
3. Introduce a structured logging helper (category, step, entity, status, reason_code, details)
4. Add startup preflight that validates critical env + DB connectivity + minimum schema before scheduling begins

This preserves the script-first architecture while substantially improving reliability and diagnosis speed.
</research_summary>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Persistent Idempotent Job Guard
Create DB-backed guard functions in data/database.py (or a dedicated helper module) to mark execution windows and detect duplicates before each job runs.

### Pattern 2: Job Boundary Wrappers
Keep existing rodar_* functions but route through a common guarded executor to standardize skip/execute/error/degraded outcomes.

### Pattern 3: Structured Event Logging
Introduce a lightweight log_event helper in scheduler.py (or utility module) to emit stable structured lines that are grep-friendly and traceable by job/key.

### Pattern 4: Boot Preflight Contract
Perform all critical startup checks once in iniciar_scheduler() and abort with actionable output if mandatory requirements are missing.

### Anti-Patterns to Avoid
- In-memory-only locks (break on restart)
- Silent except/pass around critical persistence paths
- Free-text logs without stable categories and reason codes
- Continuing startup when critical env/db/schema is invalid
</architecture_patterns>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: False idempotency
Checking only current process state or current minute can still allow duplicate execution after restart or delayed run.

### Pitfall 2: Over-failing the runtime
Treating all exceptions as fatal can reduce throughput and miss valid opportunities; isolate by fixture and elevate only critical failures.

### Pitfall 3: Log noise without signal
Verbose but inconsistent logs are hard to aggregate. Stable keys and categories matter more than volume.

### Pitfall 4: Partial startup validation
Validating only BOT_TOKEN without DB/schema checks causes failures later in the day under load.
</common_pitfalls>

## Validation Architecture

Phase 3 should use fast compile checks as quick gate plus focused runtime checks for idempotency and preflight outcomes.

- Quick checks: python -m py_compile on modified modules
- Deterministic checks: confirm idempotency table/helper presence and skip-path markers via grep
- Runtime checks: dry invocation of preflight and guarded job wrappers in non-send context where possible

Nyquist note: test infrastructure is limited today, so this phase uses command-level automated verification mapped per task and prepares clearer seams for Phase 4 automated tests.

<sources>
## Sources

### Primary (HIGH confidence)
- .planning/phases/03-operational-resilience/03-CONTEXT.md
- .planning/ROADMAP.md
- .planning/REQUIREMENTS.md
- scheduler.py
- data/database.py
- .planning/codebase/ARCHITECTURE.md
- .planning/codebase/CONCERNS.md
- .planning/codebase/CONVENTIONS.md

</sources>

---

*Phase: 03-operational-resilience*
*Research completed: 2026-03-24*
*Ready for planning: yes*
