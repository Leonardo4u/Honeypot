# Codebase Concerns

**Analysis Date:** 2026-03-24

## Tech Debt

**Monolithic orchestration in scheduler runtime:**
- Issue: `scheduler.py` concentrates scheduling, game analysis, API collection, bankroll updates, Telegram delivery, CLV/Brier updates, and Excel sync in one module with large async functions and many cross-module imports.
- Files: `scheduler.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `logs/update_excel.py`
- Impact: High regression risk when changing any workflow step; difficult to isolate failures and test specific behavior.
- Fix approach: Split into service modules (`orchestration`, `notifications`, `result-settlement`, `reporting`) and keep `scheduler.py` as thin job wiring only.

**Broad exception handling and error swallowing:**
- Issue: Extensive `except Exception` blocks, including silent `pass` in Telegram reaction handling.
- Files: `scheduler.py`, `data/steam_monitor.py`, `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/xg_understat.py`, `logs/update_excel.py`
- Impact: Real failures can be hidden, jobs may appear successful while data quality degrades.
- Fix approach: Replace broad catches with typed exceptions, add structured error context, and fail fast for critical paths (DB writes, result settlement, outbound messaging).

**Database schema ownership is fragmented:**
- Issue: Core table creation in `data/database.py` does not include columns used by inserts (`message_id_vip`, `message_id_free`, `horario`), while setup entrypoint `criar_tabelas.py` does not call `criar_banco()`.
- Files: `data/database.py`, `criar_tabelas.py`, `scheduler.py`
- Impact: Fresh setups are fragile and can fail at first insert depending on existing DB state.
- Fix approach: Create explicit migration/versioning for SQLite schema and unify setup into one deterministic bootstrap command.

## Known Bugs

**No-key fallback can silently produce zero games:**
- Symptoms: Missing `ODDS_API_KEY` triggers simulated data mode, but output game date is fixed in the past (`2025-03-18`), and formatter filters to next 12 hours.
- Files: `data/coletar_odds.py`
- Trigger: Run `buscar_jogos_com_odds()` without `ODDS_API_KEY`, then `formatar_jogos()`.
- Workaround: Provide real API key or update simulated fixture timestamp dynamically.

**Scheduler startup may proceed with invalid Telegram credentials:**
- Symptoms: Token/channel env vars are loaded but never validated before creating `Bot` and sending messages.
- Files: `scheduler.py`, `main.py`, `bot/telegram_bot.py`
- Trigger: Start app with missing/invalid `BOT_TOKEN` or channel IDs.
- Workaround: Add startup validation guard that aborts with explicit configuration errors.

## Security Considerations

**Command execution in reporting flow:**
- Risk: Shell invocation via `os.system("python gerar_xlsx.py")` is less controlled than subprocess APIs and weakens execution safety/auditability.
- Files: `logs/update_excel.py`
- Current mitigation: Command is constant string, no user input interpolation.
- Recommendations: Replace with `subprocess.run([...], check=True)` and explicit working directory.

**Operational logging may expose sensitive runtime payloads:**
- Risk: Multiple modules print exception payloads and API error text directly, which can leak operational details into logs.
- Files: `scheduler.py`, `data/coletar_odds.py`, `data/verificar_resultados.py`, `logs/update_excel.py`
- Current mitigation: No dedicated redaction layer detected.
- Recommendations: Centralize logging with redaction rules and severity levels.

## Performance Bottlenecks

**Repeated full-league API fetches inside game loops:**
- Problem: `processar_jogos()` fetches games per league and, per candidate game/market, calls `buscar_odds_todas_casas()` which performs another league-wide odds request.
- Files: `scheduler.py`, `data/steam_monitor.py`
- Cause: Missing per-cycle caching/indexing of bookmaker odds by fixture.
- Improvement path: Cache league odds once per cycle and map by fixture/team keys for downstream market checks.

**High-overhead xG update pipeline:**
- Problem: xG collection launches Selenium/ChromeDriver and sleeps for each league.
- Files: `data/xg_understat.py`
- Cause: Browser-driven scraping in scheduled update path.
- Improvement path: Isolate scraping into separate batch job with retries/cache and persist incremental diffs.

**Frequent SQLite connect/close churn:**
- Problem: Repeated short-lived SQLite connections in hot paths (monitoring, result processing, CLV updates).
- Files: `scheduler.py`, `data/database.py`, `data/steam_monitor.py`, `data/kelly_banca.py`
- Cause: Per-operation connection lifecycle rather than scoped transaction/session utilities.
- Improvement path: Introduce shared DB utility with context-managed transactions and batch updates.

## Fragile Areas

**Telegram side-effects mixed into settlement logic:**
- Files: `scheduler.py`
- Why fragile: Result settlement, bankroll update, Brier update, and message reactions happen in one loop with partial failure handling.
- Safe modification: Split settlement into idempotent steps and persist step status (`result_saved`, `bankroll_updated`, `message_updated`).
- Test coverage: No automated integration tests for partial-failure recovery detected.

**String-based team matching and parsing:**
- Files: `scheduler.py`, `data/verificar_resultados.py`, `data/steam_monitor.py`
- Why fragile: Team matching uses substring heuristics and split on `" vs "`; naming variations can break reconciliation.
- Safe modification: Persist provider fixture IDs and resolve by IDs first, names second.
- Test coverage: No fixture-matching regression tests detected.

## Scaling Limits

**Single-process scheduler with blocking loop cadence:**
- Current capacity: One process, fixed cadence (`time.sleep(60)`) and many periodic tasks in one runtime.
- Limit: As league count and active signals rise, API and DB workload concentrates in one worker.
- Scaling path: Move to queue-based workers (ingest, analyze, settle, notify) with independent schedules.

**SQLite as central mutable store under growing write frequency:**
- Current capacity: Local `edge_protocol.db` for all runtime states and snapshots.
- Limit: Concurrent writes/read-modify-write flows can become contention-prone and harder to recover.
- Scaling path: Add migration discipline now; evaluate managed relational DB if write throughput and concurrency increase.

## Dependencies at Risk

**Understat scraping stack (`selenium` + `webdriver_manager`):**
- Risk: Depends on browser/driver availability and unstable page internals (`teamsData` JS object).
- Impact: xG refresh can fail unpredictably and silently fallback to less accurate paths.
- Migration plan: Prefer stable API/data source or precomputed dataset refresh pipeline.

**Excel reporting runtime dependence (`openpyxl` + workbook shape assumptions):**
- Risk: Report updates depend on exact sheet names/offsets and can break with template changes.
- Impact: Reporting failures can interrupt post-bet bookkeeping visibility.
- Migration plan: Define workbook contract checks before write; decouple analytics store from presentation workbook.

## Missing Critical Features

**No automated test suite or CI test gate:**
- Problem: No `pytest`/`unittest` suite or test runner configuration detected; `testar_resultado.py` is a manual script.
- Blocks: Safe refactoring of scheduler/settlement logic and confidence in API integration changes.

**No schema migration/versioning mechanism:**
- Problem: DB evolution relies on ad-hoc table creation spread across modules.
- Blocks: Reproducible environment bootstrap and safe upgrades across machines.

## Test Coverage Gaps

**Orchestration and failure recovery paths untested:**
- What's not tested: Daily scheduler flow, partial failures (Telegram/DB/API), and idempotency of repeated jobs.
- Files: `scheduler.py`, `data/database.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/kelly_banca.py`
- Risk: Production-only bugs in settlement and notification ordering.
- Priority: High

**Provider integration and fallback behavior untested:**
- What's not tested: API key missing behavior, timeout/retry handling, and fixture matching edge cases.
- Files: `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/atualizar_stats.py`, `data/xg_understat.py`
- Risk: Silent empty datasets and incorrect result resolution.
- Priority: High

**Reporting update correctness untested:**
- What's not tested: Incremental workbook updates and full refresh consistency.
- Files: `logs/update_excel.py`, `data/exportar_excel.py`
- Risk: Divergent reporting without immediate detection.
- Priority: Medium

---

*Concerns audit: 2026-03-24*
