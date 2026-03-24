# Architecture

**Analysis Date:** 2026-03-24

## Pattern Overview

**Overall:** Script-oriented layered pipeline with scheduler-driven orchestration

**Key Characteristics:**
- Central orchestration in `scheduler.py` coordinates data ingestion, model scoring, filtering, staking, persistence, and notifications.
- Domain logic is split between `model/` (probability and scoring) and `data/` (API clients, DB, monitoring, bankroll, reporting).
- Imports are path-injected at runtime (`sys.path.insert`) instead of package-based imports, creating a flat module graph across `model/` and `data/`.

## Layers

**Orchestration Layer:**
- Purpose: Owns execution timing, end-to-end signal lifecycle, and cross-module coordination.
- Location: `scheduler.py`, `main.py`, `bot/telegram_bot.py`
- Contains: Async workflows, scheduled jobs, Telegram sending/reaction handling, job wrappers.
- Depends on: `model/analisar_jogo.py`, `model/filtros.py`, `data/database.py`, `data/coletar_odds.py`, `data/kelly_banca.py`, `data/clv_brier.py`, `data/steam_monitor.py`, `data/janela_monitoramento.py`.
- Used by: Process startup via `python scheduler.py` (`iniciar_bot.bat`) and ad-hoc script runs.

**Model Layer:**
- Purpose: Convert match features into probabilities, EV, EDGE score, and decision outputs.
- Location: `model/poisson.py`, `model/edge_score.py`, `model/analisar_jogo.py`, `model/filtros.py`
- Contains: Dixon-Coles-adjusted Poisson, EV/score math, gate-based filtering, signal formatting.
- Depends on: Scientific libs (`scipy`, `numpy`) and in-repo model modules.
- Used by: `scheduler.py`, `main.py`, debug scripts (`debug_hoje.py`).

**Data & Integration Layer:**
- Purpose: External API fetches, SQLite reads/writes, derived metrics, file exports.
- Location: `data/*.py`
- Contains: API adapters (`coletar_odds.py`, `verificar_resultados.py`, `atualizar_stats.py`, `xg_understat.py`), persistence (`database.py`), operational analytics (`clv_brier.py`, `steam_monitor.py`, `kelly_banca.py`).
- Depends on: `requests`, `sqlite3`, JSON files in `data/`.
- Used by: `scheduler.py`, `bot/telegram_bot.py`, utility scripts.

## Data Flow

**Signal Generation and Dispatch:**

1. Scheduled trigger invokes `rodar_analise()` in `scheduler.py`, which runs `processar_jogos()`.
2. Odds are fetched and normalized with `buscar_jogos_com_odds()` and `formatar_jogos()` from `data/coletar_odds.py`.
3. Team strength inputs are built from `calcular_xg_com_sos()` (`data/sos_ajuste.py`) and form confidence from `data/forma_recente.py`.
4. Core scoring runs through `analisar_jogo()` (`model/analisar_jogo.py`), which delegates to `model/poisson.py` and `model/edge_score.py`.
5. Rule gates and risk controls run via `aplicar_triple_gate()` (`model/filtros.py`) and Kelly sizing in `data/kelly_banca.py`.
6. Approved signals are sent to Telegram (`telegram.Bot` in `scheduler.py`) and persisted through `inserir_sinal()` in `data/database.py`.
7. Post-send side effects update CLV/Brier tracking (`data/clv_brier.py`), steam events (`data/steam_monitor.py`), and Excel sync (`logs/update_excel.py` via subprocess).

**Result Settlement and Daily Closure:**

1. Scheduled verification (`rodar_verificacao`) calls `verificar_resultados_automatico()` in `scheduler.py`.
2. Real match outcomes are fetched with `buscar_resultado_jogo()` in `data/verificar_resultados.py`.
3. Bet result is evaluated by `avaliar_mercado()` and written back through `atualizar_resultado()` in `data/database.py`.
4. Bankroll, Brier, Telegram reactions, and Excel are updated in the same orchestration flow.
5. Daily summary (`enviar_resumo_diario()`) aggregates DB + validation metrics and broadcasts status.

**State Management:**
- Durable state: SQLite database at `data/edge_protocol.db` (`data/database.py`).
- Semi-static caches: JSON files in `data/` (`medias_gols.json`, `xg_dados.json`, `forma_recente.json`, `banca_estado.json`).
- Operational reporting artifacts: `logs/relatorio_*.json` and Excel updates through `logs/update_excel.py`.

## Key Abstractions

**Signal Analysis Contract:**
- Purpose: Standard dictionary contract passed between orchestrator, model, and persistence.
- Examples: Produced in `model/analisar_jogo.py`; consumed in `scheduler.py` and persisted via `data/database.py`.
- Pattern: Dict-based payload with required keys (`liga`, `jogo`, `mercado`, `odd`, `ev`, `edge_score`, `stake_unidades`).

**Gate Pipeline:**
- Purpose: Enforce bet quality constraints before publication.
- Examples: `gate1_ev_e_odd`, `gate2_escalacao`, `gate3_odd_estavel`, `gate4_limite_diario` in `model/filtros.py`.
- Pattern: Sequential short-circuit validation returning structured reason metadata.

**Validation Telemetry:**
- Purpose: Evaluate forecast quality after bet lifecycle.
- Examples: `clv_tracking` and `brier_tracking` logic in `data/clv_brier.py`.
- Pattern: Auxiliary tables linked by `sinal_id` to primary signal records.

## Entry Points

**Scheduler Runtime:**
- Location: `scheduler.py`
- Triggers: Direct execution (`if __name__ == "__main__": iniciar_scheduler()`) and startup batch `iniciar_bot.bat`.
- Responsibilities: Register `schedule` jobs, run analysis loop, settlement loop, CLV/steam monitors, and daily summary.

**Manual/Smoke Flow:**
- Location: `main.py`
- Triggers: Direct execution with `asyncio.run(teste_completo())`.
- Responsibilities: Single-game analysis/send flow and manual result simulation.

**Interactive Bot Runtime:**
- Location: `bot/telegram_bot.py`
- Triggers: Direct execution with `app.run_polling()`.
- Responsibilities: Telegram command handlers (`/hoje`, `/banca`, `/historico`, `/resultado`).

**Schema Initialization:**
- Location: `data/database.py`, `criar_tabelas.py`
- Triggers: Direct execution.
- Responsibilities: Base table creation (`sinais`, `banca`) and validation table creation (`clv_tracking`, `brier_tracking`).

## Error Handling

**Strategy:** Localized try/except with log-and-continue behavior in long-running loops

**Patterns:**
- External calls wrapped with broad exceptions and fallback returns (for example in `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/xg_understat.py`).
- Per-game failure isolation in loops (`scheduler.py` catches and continues on individual game errors).
- Non-blocking operational side effects (Excel/CLV/steam update failures are printed but do not abort the cycle).

## Cross-Cutting Concerns

**Logging:** Print-based operational logs across orchestrator and services (for example `scheduler.py`, `data/clv_brier.py`).
**Validation:** Multi-stage gating + confidence thresholds (`model/filtros.py` + constants in `scheduler.py`: `MIN_EDGE_SCORE`, `MIN_CONFIANCA`).
**Authentication:** Environment-variable keys via `dotenv` in integration modules (`data/coletar_odds.py`, `data/verificar_resultados.py`, `data/atualizar_stats.py`, `scheduler.py`).

---

*Architecture analysis: 2026-03-24*
