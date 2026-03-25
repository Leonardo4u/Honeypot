# Runbook de Emergencia

## PB-00: Kill switch ativo
- Sintoma: envio de sinais bloqueado.
- Acao imediata:
  1. Confirmar `EDGE_KILL_SWITCH=1`.
  2. Investigar causa raiz (provider, drift, settlement).
  3. Reabilitar apenas com evidencias de estabilidade.

## PB-01: Breach de disponibilidade de ciclo
- Acao:
  1. Consultar `job_execucoes` por `status=failed`.
  2. Corrigir job com maior taxa de falha.
  3. Validar com `python scripts/smoke_test.py`.

## PB-02: Breach de fallback/provider
- Acao:
  1. Validar APIs externas e credenciais.
  2. Reduzir risco: ativar canary (`EDGE_CANARY_ENABLED=1`, `EDGE_CANARY_RATIO=0.2`).
  3. Se mantiver > limiar, ativar kill switch.

## PB-03: Breach de latencia
- Acao:
  1. Analisar etapa lenta no log de ciclo.
  2. Verificar timeout de chamadas externas.
  3. Escalar janelas de execucao se necessario.

## PB-04: Drift de qualidade (Brier)
- Acao:
  1. Revisar `quality_trends` e segmentos afetados.
  2. Executar `python scripts/backtest_moving_window.py`.
  3. Manter canary ate normalizacao.

## PB-05: Hard risk limit (perda/exposicao)
- Acao:
  1. Bloquear novos envios (automatico).
  2. Revisar sinais abertos e concentracao por jogo.
  3. Ajustar limites apenas apos analise formal.
