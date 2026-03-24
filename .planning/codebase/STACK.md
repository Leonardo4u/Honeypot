# Technology Stack

**Analysis Date:** 2026-03-24

## Languages

**Primary:**
- Python (version not pinned) - Core application and automation scripts across `main.py`, `scheduler.py`, `data/*.py`, `model/*.py`, and `bot/telegram_bot.py`.

**Secondary:**
- Windows Batch (`.bat`) - Local startup launcher in `iniciar_bot.bat`.
- JSON (data format) - Local persisted model/input/output artifacts such as `data/medias_gols.json`, `data/xg_dados.json`, `data/banca_estado.json`, `logs/relatorio_2026-03-22.json`.

## Runtime

**Environment:**
- CPython runtime invoked via `python` command in `iniciar_bot.bat` and subprocess calls in `scheduler.py`.
- OS integration indicates Windows-oriented operation (`shell:startup` guidance inside `iniciar_bot.bat`).

**Package Manager:**
- `pip` (inferred) - Explicit installation hint in `data/exportar_excel.py` (`pip install openpyxl`).
- Lockfile: missing (no `requirements.txt`, `pyproject.toml`, `Pipfile.lock`, or `poetry.lock` detected in workspace root).

## Frameworks

**Core:**
- `python-telegram-bot` (version not pinned) - Bot messaging and command handlers in `main.py`, `scheduler.py`, and `bot/telegram_bot.py`.
- `python-dotenv` (version not pinned) - Environment loading through `load_dotenv()` in `main.py`, `scheduler.py`, and multiple `data/*.py` modules.

**Testing:**
- Not detected (no `pytest`, `unittest` suite files, or dedicated test config detected).

**Build/Dev:**
- `schedule` (version not pinned) - Cron-like task scheduling in `scheduler.py`.
- `selenium` + `webdriver-manager` (versions not pinned) - Browser automation scraping from Understat in `data/xg_understat.py`.

## Key Dependencies

**Critical:**
- `requests` - HTTP client for external odds/football APIs in `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/atualizar_stats.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`.
- `sqlite3` (stdlib) - Persistent operational database across `data/database.py`, `scheduler.py`, `data/kelly_banca.py`, `data/clv_brier.py`, `data/steam_monitor.py`, `data/janela_monitoramento.py`.
- `python-telegram-bot` - Signal/result delivery path in `main.py`, `scheduler.py`, `bot/telegram_bot.py`.

**Infrastructure:**
- `openpyxl` - Excel reporting and dashboard generation in `data/exportar_excel.py` and `logs/update_excel.py`.
- `numpy` + `scipy` - Probabilistic modeling (`Poisson`, optimization) in `model/poisson.py`.
- `selenium` + `webdriver-manager` - Understat xG extraction in `data/xg_understat.py`.

## Configuration

**Environment:**
- Runtime secrets and IDs are loaded from `.env` via `load_dotenv()` in `main.py`, `scheduler.py`, `bot/telegram_bot.py`, and data modules.
- Key config variables (names only): `BOT_TOKEN`, `CANAL_FREE`, `CANAL_VIP`, `ODDS_API_KEY`, `API_FOOTBALL_KEY` (read via `os.getenv(...)` in `main.py`, `scheduler.py`, `data/coletar_odds.py`, `data/verificar_resultados.py`, `data/atualizar_stats.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`).

**Build:**
- No formal build system detected.
- Operational entrypoints are script-driven: `scheduler.py`, `main.py`, and `bot/telegram_bot.py`.

## Platform Requirements

**Development:**
- Python environment with manually installed third-party packages (no pinned manifest).
- Chrome/Chromium availability required for Selenium flow in `data/xg_understat.py`.

**Production:**
- Long-running process model using in-process scheduler loop (`schedule.run_pending()` in `scheduler.py`).
- Local file and SQLite persistence expected (`data/edge_protocol.db`, JSON files in `data/`, spreadsheets in `logs/`).
- Telegram + external football/odds APIs required for full functionality.

---

*Stack analysis: 2026-03-24*
