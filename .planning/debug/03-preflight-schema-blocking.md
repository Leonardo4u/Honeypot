# Debug Session: 03-preflight-schema-blocking

## Symptom Summary
- Scheduler inicia e fecha imediatamente no .bat.
- Execucao manual mostra preflight failed com: Schema minimo incompleto: job_execucoes.
- Testes de fase 03 apos startup ficam inviabilizados por falha no bootstrap.

## Root Cause
- Ordem de startup em scheduler.py executa preflight antes de garantir criacao da tabela job_execucoes.
- O preflight exige job_execucoes no schema minimo e interrompe com SystemExit(1) antes de garantir_tabela_execucoes().
- Em execucao via .bat, o terminal fecha ao sair com erro, reduzindo observabilidade para o operador.

## Evidence
- iniciar_scheduler() chama executar_preflight() antes de garantir_tabela_execucoes().
- Log runtime: critical_preflight_failed com falha em job_execucoes.
- Codigo retornado no terminal: Exit Code 1.

## Files Involved
- scheduler.py
- data/database.py
- iniciar_bot.bat

## Suggested Fix Direction
1. Garantir bootstrap de schema de job_execucoes antes da validacao de schema minimo.
2. Manter preflight para validar restante do estado critico sem falso negativo de tabela bootstrap.
3. Melhorar observabilidade do .bat com pausa condicional em erro e opcao de log em arquivo.
