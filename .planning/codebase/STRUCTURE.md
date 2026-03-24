# Codebase Structure

**Analysis Date:** 2026-03-24

## Directory Layout

```text
edge_protocol/
├── bot/                    # Telegram command bot runtime
├── data/                   # Persistence, APIs, monitoring, bankroll, exports
├── logs/                   # Generated daily reports and Excel updater script
├── model/                  # Probability model, scoring, and gating logic
├── .planning/codebase/     # Generated mapping documentation
├── main.py                 # Manual end-to-end smoke flow
├── scheduler.py            # Production scheduler/orchestrator entrypoint
└── *.py                    # Utility/debug/bootstrap scripts at repo root
```

## Directory Purposes

**`model/`:**
- Purpose: Pure-ish domain/model logic for pricing and decisioning.
- Contains: `poisson.py`, `edge_score.py`, `analisar_jogo.py`, `filtros.py`.
- Key files: `model/analisar_jogo.py`, `model/poisson.py`.

**`data/`:**
- Purpose: Data access and external integration boundary.
- Contains: SQLite access (`database.py`), API clients (`coletar_odds.py`, `verificar_resultados.py`), bankroll/telemetry (`kelly_banca.py`, `clv_brier.py`, `steam_monitor.py`), support datasets (`*.json`).
- Key files: `data/database.py`, `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/janela_monitoramento.py`.

**`bot/`:**
- Purpose: Telegram command handlers for operational querying.
- Contains: `telegram_bot.py`.
- Key files: `bot/telegram_bot.py`.

**`logs/`:**
- Purpose: Runtime report artifacts and Excel update bridge.
- Contains: `relatorio_*.json`, `update_excel.py`, helper docs.
- Key files: `logs/update_excel.py`.

**Repo root scripts:**
- Purpose: Runtime entrypoints and one-off operations.
- Contains: `scheduler.py`, `main.py`, `criar_tabelas.py`, debug/test scripts (`debug_hoje.py`, `testar_resultado.py`, `verificar_jogos_hoje.py`).
- Key files: `scheduler.py`, `main.py`, `iniciar_bot.bat`.

## Key File Locations

**Entry Points:**
- `scheduler.py`: Main scheduled runtime (`iniciar_scheduler()`).
- `main.py`: Manual async simulation (`teste_completo()`).
- `bot/telegram_bot.py`: Telegram polling bot (`app.run_polling()`).
- `criar_tabelas.py`: DB auxiliary table setup.

**Configuration:**
- `.env`: Environment configuration file present (contents not analyzed).
- `iniciar_bot.bat`: Windows startup launcher calling `python scheduler.py`.

**Core Logic:**
- `model/analisar_jogo.py`: Signal analysis composition and output contract.
- `model/poisson.py`: Probability engine with Dixon-Coles corrections.
- `model/filtros.py`: Gate-based hard filters.
- `data/kelly_banca.py`: Position sizing and bankroll controls.

**Testing:**
- Not detected as a dedicated test suite (`tests/`, `pytest`, `unittest` structure not present).
- Script-style checks exist at root (`debug_hoje.py`, `debug_exposicao.py`, `testar_resultado.py`).

## Naming Conventions

**Files:**
- Python modules mostly use `snake_case.py`: `verificar_resultados.py`, `janela_monitoramento.py`.
- Root utility scripts also follow snake_case naming: `buscar_liga_europa.py`, `verificar_jogos_hoje.py`.

**Directories:**
- Short functional buckets in lowercase: `model`, `data`, `bot`, `logs`.

## Where to Add New Code

**New Feature:**
- Primary code: Add orchestration in `scheduler.py` only if it is a scheduled workflow; place reusable logic in `model/` or `data/` first.
- Tests: Add script-based verification at root following existing style (`debug_<tema>.py`) until a formal test harness exists.

**New Component/Module:**
- Implementation: 
  - Model/math/rules -> `model/<feature>.py`
  - API/DB/integration/reporting -> `data/<feature>.py`
  - Telegram command surface -> `bot/telegram_bot.py` (add handler + function)

**Utilities:**
- Shared helpers: Keep domain helpers inside the closest existing functional module in `data/` or `model/` (the codebase currently avoids a generic utils package).

## Special Directories

**`.planning/codebase/`:**
- Purpose: Persistent codebase analysis documents used by planning/execution commands.
- Generated: Yes.
- Committed: Yes.

**`data/__pycache__/` and `model/__pycache__/`:**
- Purpose: Python bytecode caches.
- Generated: Yes.
- Committed: No (should remain untracked).

**`logs/`:**
- Purpose: Runtime-generated reporting data and update bridge script.
- Generated: Mixed (JSON reports generated; `update_excel.py` maintained source).
- Committed: Yes for script/docs; report JSONs currently present in workspace.

---

*Structure analysis: 2026-03-24*
