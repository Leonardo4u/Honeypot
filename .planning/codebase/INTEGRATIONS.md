# External Integrations

**Analysis Date:** 2026-03-24

## APIs & External Services

**Sports Odds & Market Data:**
- The Odds API (`api.the-odds-api.com`) - Fetches odds, market books, and bookmaker snapshots.
  - SDK/Client: `requests` in `data/coletar_odds.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`.
  - Auth: `ODDS_API_KEY` via `os.getenv(...)` in `data/coletar_odds.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`.

**Football Fixtures & Standings Data:**
- API-Football (`v3.football.api-sports.io`) - Used for league standings/stat updates and match result verification.
  - SDK/Client: `requests` in `data/atualizar_stats.py` and `data/verificar_resultados.py`.
  - Auth: `API_FOOTBALL_KEY` in `data/atualizar_stats.py` and `data/verificar_resultados.py`.

**xG Source (Scraped):**
- Understat (`understat.com`) - Headless browser scraping for xG historical features.
  - SDK/Client: `selenium` + `webdriver-manager` in `data/xg_understat.py`.
  - Auth: Not required (public web source).

**Messaging & Delivery:**
- Telegram Bot API - Sends betting signals and summaries, and handles command interface.
  - SDK/Client: `telegram` / `telegram.ext` in `main.py`, `scheduler.py`, `bot/telegram_bot.py`.
  - Auth: `BOT_TOKEN`; channel routing via `CANAL_FREE` and `CANAL_VIP`.

## Data Storage

**Databases:**
- SQLite (local file) at `data/edge_protocol.db`.
  - Connection: direct local path (no network connection string), e.g., `sqlite3.connect("data/edge_protocol.db")` in `scheduler.py` and `DB_PATH` usage in `data/database.py`.
  - Client: Python stdlib `sqlite3` (`data/database.py`, `data/kelly_banca.py`, `data/clv_brier.py`, `data/steam_monitor.py`, `data/janela_monitoramento.py`).

**File Storage:**
- Local filesystem only.
  - JSON artifacts in `data/*.json` and `logs/*.json`.
  - Excel output in `logs/edge_protocol_resultados.xlsx` produced by `data/exportar_excel.py` and updated through `logs/update_excel.py`.

**Caching:**
- None as dedicated service; persistence/caching behavior is file/SQLite based.

## Authentication & Identity

**Auth Provider:**
- Custom token-based service auth using environment variables.
  - Implementation: `python-dotenv` + `os.getenv(...)` in `main.py`, `scheduler.py`, `bot/telegram_bot.py`, and `data/*.py` API modules.

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry/New Relic/Bugsnag client imports).

**Logs:**
- Print-based runtime diagnostics (`print(...)` across scripts, especially `scheduler.py`, `data/*`).
- Operational JSON reports present in `logs/` (for example `logs/relatorio_2026-03-22.json`).

## CI/CD & Deployment

**Hosting:**
- Not detected as managed cloud deployment; appears to be local/VM process execution.

**CI Pipeline:**
- None detected (no GitHub Actions/Jenkins/GitLab CI manifests found in repo root).

## Environment Configuration

**Required env vars:**
- `BOT_TOKEN` - Telegram bot authentication (`main.py`, `scheduler.py`, `bot/telegram_bot.py`).
- `CANAL_FREE` - Telegram free channel target (`main.py`, `scheduler.py`, `bot/telegram_bot.py`).
- `CANAL_VIP` - Telegram VIP channel target (`main.py`, `scheduler.py`, `bot/telegram_bot.py`).
- `ODDS_API_KEY` - Odds API access (`data/coletar_odds.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`).
- `API_FOOTBALL_KEY` - API-Football access (`data/atualizar_stats.py`, `data/verificar_resultados.py`).

**Secrets location:**
- `.env` file at repository root is present and loaded by multiple modules.

## Webhooks & Callbacks

**Incoming:**
- None detected (Telegram usage is polling/command handlers in `bot/telegram_bot.py`, not webhook handlers).

**Outgoing:**
- HTTPS requests to The Odds API, API-Football, and Understat pages (`data/coletar_odds.py`, `data/steam_monitor.py`, `data/clv_brier.py`, `data/janela_monitoramento.py`, `data/atualizar_stats.py`, `data/verificar_resultados.py`, `data/xg_understat.py`).
- Outbound Telegram Bot API message calls in `main.py` and `scheduler.py`.

---

*Integration audit: 2026-03-24*
