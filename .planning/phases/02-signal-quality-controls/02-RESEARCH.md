# Phase 2: Signal Quality Controls - Research

**Researched:** 2026-03-24
**Domain:** Signal gating transparency, threshold governance, and staking/persistence integrity
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md found for this phase.

### Locked Decisions
- None

### the agent's Discretion
- How to centralize threshold constants
- How to structure reject-reason payloads
- How to enforce stake safety caps in edge cases

### Deferred Ideas (OUT OF SCOPE)
- UI/dashboard and frontend analytics
- Multi-tenant workflows
</user_constraints>

<research_summary>
## Summary

Current gate logic already returns useful messages in `model/filtros.py`, but threshold values are hardcoded and spread through modules (for example, `MIN_EDGE_SCORE`, `MIN_CONFIANCA` in `scheduler.py` and market thresholds in `model/filtros.py`). This creates drift risk and low auditability.

Stake sizing in `data/kelly_banca.py` has multiple protections, but malformed input cases still rely on implicit assumptions. CLV/Brier tracking in `data/clv_brier.py` links by `sinal_id`, yet there are no explicit integrity checks preventing orphan or duplicate tracking states.

**Primary recommendation:** Introduce a centralized signal-policy module for thresholds/gate metadata, then add explicit integrity guards for stake sizing and tracking linkage.
</research_summary>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Centralized Signal Policy
Move threshold constants to one module consumed by `scheduler.py` and `model/filtros.py`.

### Pattern 2: Structured Reject Reasons
Ensure every gate rejection returns machine-friendly reason code + human message.

### Pattern 3: Integrity Before Side Effects
Validate `sinal_id` linkage and payload consistency before CLV/Brier writes.

### Anti-Patterns to Avoid
- Threshold literals duplicated across files.
- Free-text-only rejection messages without stable codes.
- Stake/tracking updates without explicit bounds and foreign-key style checks.
</architecture_patterns>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Threshold drift
Different files evolve independently and produce inconsistent approval decisions.

### Pitfall 2: Hidden reject logic
Logs show message text but no stable code for aggregation/auditing.

### Pitfall 3: Tracking orphan records
Async or partial failures create CLV/Brier rows without matching signal lifecycle context.
</common_pitfalls>

<sources>
## Sources

### Primary (HIGH confidence)
- `model/filtros.py`
- `scheduler.py`
- `data/kelly_banca.py`
- `data/clv_brier.py`
- `data/database.py`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
</sources>

---

*Phase: 02-signal-quality-controls*
*Research completed: 2026-03-24*
*Ready for planning: yes*
