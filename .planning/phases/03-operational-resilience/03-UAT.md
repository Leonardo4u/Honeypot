---
status: diagnosed
phase: 03-operational-resilience
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md]
started: 2026-03-24T10:42:40.9166225-03:00
updated: 2026-03-24T11:04:25.2580411-03:00
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Com todos os processos do bot encerrados, iniciar o scheduler do zero. O boot deve completar sem erro de inicializacao e sem traceback. O scheduler deve entrar em modo ativo e exibir os marcos de boot/preflight.
result: pass

### 2. Preflight Bloqueia Falha Critica
expected: Removendo BOT_TOKEN ou CANAL_VIP do ambiente e iniciando o scheduler, o preflight deve falhar com mensagem acionavel e interromper o processo (SystemExit).
result: issue
reported: "Preflight retornou pass e scheduler seguiu para boot ready; nao ocorreu bloqueio critico de env vars."
severity: major

### 3. Preflight Warning Nao Critico
expected: Com variaveis criticas corretas e arquivo de Excel ausente, o preflight deve emitir warning nao critico e continuar o startup normalmente.
result: issue
reported: "Preflight retornou pass sem warning; cenario de Excel ausente nao foi validado nessa execucao."
severity: major

### 4. Idempotencia por Janela
expected: Acionando o mesmo job duas vezes na mesma janela de execucao, a segunda tentativa deve ser ignorada com evento de idempotent_skip, sem duplicar processamento.
result: pass

### 5. Isolamento de Falha por Item
expected: Se um item/jogo falhar durante processamento, o ciclo nao deve abortar por completo; os demais itens continuam e o ciclo pode ser marcado como degraded quando falha critica de persistencia ocorrer.
result: issue
reported: "Execucao seguiu normal com idempotent_skip; nao houve cenario de falha por item para validar isolamento/degraded."
severity: major

### 6. Logs Estruturados de Diagnostico
expected: Durante boot e ciclo, os logs devem incluir eventos estruturados para boot start/ready, preflight start/pass/fail, job guard start/skip/end e cycle_totals com contexto util para triagem diaria.
result: pass

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "O boot deve completar sem erro de inicializacao e sem traceback, entrando em modo ativo"
  status: resolved
  reason: "Reteste comprovou startup completo com boot/preflight pass e scheduler ativo."
  severity: blocker
  test: 1
  root_cause: "Preflight executa antes de garantir bootstrap da tabela job_execucoes e encerra com SystemExit(1), fazendo o processo fechar no .bat."
  artifacts:
    - path: "scheduler.py"
      issue: "Ordem de startup valida schema antes de garantir tabela job_execucoes"
    - path: "iniciar_bot.bat"
      issue: "Nao preserva console para leitura do erro ao sair com code 1"
  missing:
    - "Garantir criacao de job_execucoes antes do validar_schema_minimo no startup"
    - "Adicionar pausa condicional em erro no .bat para observabilidade"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Ao remover BOT_TOKEN ou CANAL_VIP, o preflight deve falhar com mensagem acionavel e encerrar"
  status: failed
  reason: "User reported: Preflight retornou pass e scheduler seguiu para boot ready; nao ocorreu bloqueio critico de env vars."
  severity: major
  test: 2
  root_cause: "Reteste executado com startup normal nao demonstrou a condicao de env removido; necessario validar explicitamente sem BOT_TOKEN ou sem CANAL_VIP."
  artifacts:
    - path: "scheduler.py"
      issue: "Fluxo de preflight precisa ser validado em cenario controlado de ausencia de env"
  missing:
    - "Executar reteste removendo BOT_TOKEN ou CANAL_VIP para confirmar bloqueio fail-fast"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Com variaveis criticas corretas e Excel ausente, o preflight deve avisar e manter startup"
  status: failed
  reason: "User reported: Preflight retornou pass sem warning; cenario de Excel ausente nao foi validado nessa execucao."
  severity: blocker
  test: 3
  root_cause: "Reteste atual nao simulou ausencia do arquivo de Excel, portanto o ramo de warning nao critico nao foi exercitado."
  artifacts:
    - path: "scheduler.py"
      issue: "Necessario validar explicitamente o caminho de warning non_critical_excel_missing"
  missing:
    - "Executar reteste com logs/update_excel.py temporariamente ausente para confirmar warning nao critico"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "A segunda execucao na mesma janela deve ser ignorada com idempotent_skip"
  status: resolved
  reason: "Reteste exibiu evento job_guard skip com reason_code idempotent_skip."
  severity: major
  test: 4
  root_cause: "Scheduler nao inicia devido ao preflight de schema; jobs nao chegam a executar e nao e possivel observar idempotent_skip."
  artifacts:
    - path: "scheduler.py"
      issue: "Execucao abortada antes de rodar wrappers guardados"
  missing:
    - "Desbloquear startup corrigindo schema bootstrap"
    - "Rodar reteste especifico de dupla execucao na mesma janela"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Falhas por item nao devem derrubar o ciclo inteiro e devem permitir continuidade com degradacao controlada"
  status: failed
  reason: "User reported: Execucao seguiu normal com idempotent_skip; nao houve cenario de falha por item para validar isolamento/degraded."
  severity: blocker
  test: 5
  root_cause: "Reteste nao injetou uma falha real por item no processamento; portanto o comportamento de isolamento e marcacao degraded nao foi exercitado."
  artifacts:
    - path: "scheduler.py"
      issue: "Caminho de degraded depende de falha operacional real durante processamento"
  missing:
    - "Executar reteste com falha controlada em um item para validar continuidade dos demais"
    - "Confirmar log/evento degraded durante falha e fechamento normal do job"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Logs estruturados devem cobrir boot/preflight e ciclo (job guard/cycle_totals) para diagnostico"
  status: resolved
  reason: "Reteste exibiu logs estruturados de boot/preflight/job_guard/cycle_totals com status ok."
  severity: blocker
  test: 6
  root_cause: "Logs de boot/preflight estao presentes, mas logs de ciclo nao aparecem porque startup e interrompido no preflight."
  artifacts:
    - path: "scheduler.py"
      issue: "Interrupcao no preflight impede emissao de logs de job guard e cycle_totals"
  missing:
    - "Corrigir bloqueio de schema para permitir logs completos de ciclo"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
