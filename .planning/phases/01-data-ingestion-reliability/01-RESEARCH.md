# Phase 1: Data Ingestion Reliability - Research

**Researched:** 2026-03-24
**Domain:** Python data-ingestion resilience for API + scraping inputs
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md found for this phase.

### Locked Decisions
- None

### the agent's Discretion
- Retry strategy implementation details
- Structured logging format
- Where to place shared resilience utilities

### Deferred Ideas (OUT OF SCOPE)
- UI/dashboard features
- Multi-tenant architecture changes
</user_constraints>

<research_summary>
## Summary

The current ingestion flow is centralized in `scheduler.py`, with data sources spread across `data/coletar_odds.py`, `data/verificar_resultados.py`, and `data/xg_understat.py`. Failures are mostly handled by broad `except` blocks returning empty payloads, which keeps runtime alive but loses diagnostic quality and creates inconsistent fallback behavior.

The standard reliability pattern for this codebase should be: bounded retries for transient failures, explicit error classification, validated input contracts before model execution, and per-run provider health summary. This matches the current script-oriented architecture and can be implemented incrementally without replatforming.

**Primary recommendation:** Add a shared ingestion resilience helper in `data/` and route scheduler ingestion calls through it before adding provider-level health rollups.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | current | HTTP calls to odds/results providers | Already used throughout `data/` |
| sqlite3 | stdlib | Durable state and diagnostics persistence | Existing project storage layer |
| json | stdlib | Structured health/log payloads | Existing reporting pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time | stdlib | Retry backoff waits | Retry wrappers |
| datetime | stdlib | Timestamped health events | Run-level observability |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom retry helper | tenacity | Good library, but adds dependency and migration overhead for a script-first codebase |

**Installation:**
No new dependency required for Phase 1 baseline.
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Pattern 1: Shared Resilience Boundary
**What:** Add one reusable helper for retry + classification, then call it from provider modules.
**When to use:** Any external API call (`requests.get`).

### Pattern 2: Validate Before Analysis
**What:** Validate required fields (`home_team`, `away_team`, `odds`, xG/form values) before calling `analisar_jogo()`.
**When to use:** Right after `formatar_jogos()` and before loop-level scoring.

### Pattern 3: Provider Health Rollup
**What:** Aggregate provider outcomes (`ok`, `timeout`, `http_error`, `empty_payload`, `fallback_used`) per run.
**When to use:** End of `processar_jogos()` and end of verification loops.

### Anti-Patterns to Avoid
- Silent catch-and-return without error category.
- Mixing retry policy logic in every module.
- Running model analysis on malformed input without explicit fallback marker.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-module ad hoc retry loops | Custom while loops in each file | One helper in `data/` | Avoid policy drift |
| Free-form print errors | Inconsistent log strings | Structured status dicts | Better diagnostics and summaries |
| Implicit defaulting | Hidden fallback behavior | Explicit fallback tags in payload | Improves auditability |
</dont_hand-roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Retry storms
**What goes wrong:** Aggressive retries amplify provider failures.
**How to avoid:** Cap attempts and use bounded backoff.

### Pitfall 2: False success on empty payload
**What goes wrong:** Empty list treated as healthy ingestion.
**How to avoid:** Distinguish `empty_payload` from `ok` in health summary.

### Pitfall 3: Model crash from missing fields
**What goes wrong:** Missing team/odd/xG values propagate to scoring path.
**How to avoid:** Enforce input validation gate with skip + reason metadata.
</common_pitfalls>

<sources>
## Sources

### Primary (HIGH confidence)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/STACK.md`
- `scheduler.py`
- `data/coletar_odds.py`
- `data/verificar_resultados.py`
- `data/xg_understat.py`
- `data/forma_recente.py`
- `data/sos_ajuste.py`
</sources>

---

*Phase: 01-data-ingestion-reliability*
*Research completed: 2026-03-24*
*Ready for planning: yes*
