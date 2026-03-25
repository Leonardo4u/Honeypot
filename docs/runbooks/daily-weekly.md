# Runbook Operacional (Diario/Semanal)

## Diario
1. Rodar `python scripts/check_repo_hygiene.py`.
2. Rodar `python scripts/smoke_test.py`.
3. Verificar painel SLO: `python scripts/slo_panel.py` e revisar `logs/slo_panel_latest.json`.
4. Confirmar que nao ha alertas `critical` recentes em `operation_alerts`.
5. Validar resumo diario enviado para o canal VIP/FREE.

## Semanal
1. Rodar `python scripts/backtest_moving_window.py`.
2. Validar promocao: `python scripts/check_promotion_gate.py`.
3. Revisar `quality_trends` (global + mercado) para deriva de Brier e fallback.
4. Validar disponibilidade de ciclo (ultimos 7 dias) >= 95%.
5. Revisar limites de risco:
   - `EDGE_MAX_DAILY_LOSS_UNITS`
   - `EDGE_MAX_EXPOSURE_WINDOW_UNITS`

## Cadencia de manutencao
- Segunda 06:00: stats + xG.
- Segunda 06:30: backtest janela movel.
- Todo push/PR: CI obrigatorio.
