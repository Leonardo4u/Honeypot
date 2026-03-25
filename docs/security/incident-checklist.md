# Checklist de Incidentes

## 1) Vazamento de chave
- [ ] Ativar `EDGE_KILL_SWITCH=1`.
- [ ] Revogar e rotacionar chaves expostas.
- [ ] Verificar acessos indevidos recentes.
- [ ] Registrar incidente e impacto.

## 2) Provider fora/instavel
- [ ] Verificar `provider_error_rate` e `fallback_rate`.
- [ ] Ativar canary (20%) antes de retorno total.
- [ ] Se persistir degradacao, manter kill switch.
- [ ] Abrir acompanhamento com timestamp e evidencias.

## 3) Settlement inconsistente
- [ ] Pausar fechamento automatico se necessario.
- [ ] Auditar fixtures e janela por liga.
- [ ] Rodar validacoes focadas (`tests.test_scheduler_settlement_integrity`).
- [ ] Corrigir e reprocessar com trilha de auditoria.

## 4) Drift de performance
- [ ] Rodar backtest de janela movel.
- [ ] Validar gate de promocao.
- [ ] Operar em canary ate recuperar envelope.
