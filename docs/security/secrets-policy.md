# Politica de Segredos e Permissoes Minimas

## Segredos
- `BOT_TOKEN`, `ODDS_API_KEY`, `API_FOOTBALL_KEY` sao obrigatorios e nao podem ser versionados.
- Rotacao recomendada: a cada 30 dias ou apos incidente.
- Rotacao obrigatoria: suspeita de vazamento ou acesso indevido.

## Permissao minima
- Bot Telegram: apenas permissao necessaria para envio/reacao no(s) canal(is) autorizados.
- API keys: escopos minimos, sem permissoes administrativas desnecessarias.

## Auditoria
- Toda acao sensivel deve gerar trilha em `operation_audit`:
  - ativacao de kill switch,
  - bloqueios hard de risco,
  - alertas criticos.

## Boas praticas
- Nunca registrar segredos em logs.
- Nunca compartilhar `.env`.
- Revisar permissao de canais e tokens em toda release.
