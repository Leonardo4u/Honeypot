# Coding Conventions

**Analysis Date:** 2026-03-24

## Naming Patterns

**Files:**
- Use `snake_case.py` for modules and scripts.
- Domain-oriented names in Portuguese are standard for business logic and data flows.
- Evidence: `scheduler.py`, `model/analisar_jogo.py`, `data/verificar_resultados.py`, `data/steam_monitor.py`, `logs/update_excel.py`.

**Functions:**
- Use `snake_case` function names, including orchestrators and helpers.
- Prefer verb-first naming for actions (`buscar_`, `atualizar_`, `calcular_`, `formatar_`).
- Evidence: `buscar_jogos_com_odds()` in `data/coletar_odds.py`, `calcular_probabilidades()` in `model/poisson.py`, `aplicar_triple_gate()` in `model/filtros.py`, `iniciar_scheduler()` in `scheduler.py`.

**Variables:**
- Use `snake_case` for local variables and module constants.
- Uppercase constants for config/global values.
- Evidence: `MAX_SINAIS_DIA`, `MIN_EDGE_SCORE`, `LIGA_KEY_MAP` in `scheduler.py`; `DB_PATH` in `data/database.py`; `RHO_POR_LIGA` in `model/poisson.py`.

**Types:**
- No explicit typing system is enforced (no type hints observed).
- Data contracts are dictionary-based and documented with docstrings/comments.
- Evidence: `analisar_jogo(dados)` in `model/analisar_jogo.py`; payload dictionaries in `scheduler.py` and `logs/update_excel.py`.

## Code Style

**Formatting:**
- Tool used: Not detected.
- Key settings: Not detected (no `pyproject.toml`, no formatter config found).
- In practice, code uses 4-space indentation and mostly double-quoted strings.
- Evidence: `main.py`, `scheduler.py`, `data/xg_understat.py`, `model/edge_score.py`.

**Linting:**
- Tool used: Not detected.
- Key rules: Not applicable (no Flake8/Ruff/Pylint config found).

## Import Organization

**Order:**
1. Python standard library imports first.
2. Third-party packages second.
3. Local module imports third.

**Path Aliases:**
- No formal alias system detected.
- Local imports are enabled via runtime path mutation with `sys.path.insert(...)`.
- Evidence: `main.py`, `scheduler.py`, `bot/telegram_bot.py`, `debug_hoje.py`.

## Error Handling

**Patterns:**
- Guard external IO/network calls with broad `try/except` and return fallback values (`[]`, `{}`, `None`).
- Log exceptions to console with contextual messages and continue pipeline when possible.
- Evidence: `data/coletar_odds.py` (`requests` fallback), `data/xg_understat.py` (Selenium fallback), `scheduler.py` (per-stage `try/except` around CLV/Excel/Brier/steam).

## Logging

**Framework:** `print` (console output).

**Patterns:**
- Structured operational logs with f-strings are the default runtime observability mechanism.
- Use status prefixes and contextual fields in long-running jobs.
- Evidence: `scheduler.py` (scheduler lifecycle and signal logs), `logs/update_excel.py` (`log()` helper writes console + file), `data/dashboard_validacao.py` (terminal dashboard output).

## Comments

**When to Comment:**
- Use concise section separators for large modules.
- Use inline comments to mark business sub-steps (CLV, steam, Excel update).
- Evidence: section banners in `model/poisson.py` and `logs/update_excel.py`; inline stage comments in `scheduler.py`.

**JSDoc/TSDoc:**
- Not applicable for this Python codebase.
- Python docstrings are used on key functions and entry points.
- Evidence: `model/analisar_jogo.py`, `model/edge_score.py`, `data/verificar_resultados.py`.

## Function Design

**Size:**
- Small pure functions for math/business rules in `model/` and many modules under `data/`.
- Large orchestration functions exist where workflows are centralized.
- Evidence: compact calculators in `model/edge_score.py`; large pipeline `processar_jogos()` in `scheduler.py`.

**Parameters:**
- Function inputs are commonly primitive parameters or flexible dict payloads.
- Dict payloads are preferred for cross-module contracts.
- Evidence: `analisar_jogo(dados)` in `model/analisar_jogo.py`; `aplicar_triple_gate(dados_sinal)` in `model/filtros.py`; payload actions in `logs/update_excel.py`.

**Return Values:**
- Prefer dictionaries carrying both computed values and metadata for downstream steps.
- Use `None`/empty container sentinels for unavailable data.
- Evidence: returns in `model/poisson.py`, `model/analisar_jogo.py`, `data/coletar_odds.py`, `data/verificar_resultados.py`.

## Module Design

**Exports:**
- Modules export top-level functions directly; no package-based API layer detected.
- Reuse occurs by direct function imports across folders.
- Evidence: imports from `scheduler.py` spanning `model/` and `data/`; imports in `main.py` and `bot/telegram_bot.py`.

**Barrel Files:**
- Not used.

---

*Convention analysis: 2026-03-24*
