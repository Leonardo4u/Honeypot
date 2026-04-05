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

## Sync semanal de outcomes

**Quando:** toda segunda-feira antes de rodar o calibrate.py  
**Comando:**
python picks_log.py --sync-db data/edge_protocol.db

**Verificacao obrigatoria pos-sync:**
python -c "
import csv
rows = list(csv.DictReader(open('data/picks_log.csv')))
settled = [r for r in rows if r.get('outcome') in ('0','1')]
print(f'Settled: {len(settled)} | Total: {len(rows)}')
"

**Threshold para calibracao:** minimo 30 settled antes de rodar calibrate.py  
**Se pending > 0:** verificar se jogos ainda nao foram finalizados no banco ou se ha falha de match por prediction_id

## Ordem semanal de execucao (calibracao)
1. `python picks_log.py --sync-db data/edge_protocol.db`
2. Verificar volume settled
3. `python calibrate.py ...` (somente se settled >= 30)
4. `python calibrar_modelo.py --build-ligas --min-matches 50`

## Cadencia de manutencao
- Segunda 06:00: stats + xG.
- Segunda 06:30: backtest janela movel.
- Todo push/PR: CI obrigatorio.
