---
status: diagnosed
phase: 03-operational-resilience
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md]
started: 2026-03-24T10:42:40.9166225-03:00
updated: 2026-03-24T10:50:34.7374443-03:00
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Com todos os processos do bot encerrados, iniciar o scheduler do zero. O boot deve completar sem erro de inicializacao e sem traceback. O scheduler deve entrar em modo ativo e exibir os marcos de boot/preflight.
result: issue
reported: "iniciei e fechou"
severity: blocker

### 2. Preflight Bloqueia Falha Critica
expected: Removendo BOT_TOKEN ou CANAL_VIP do ambiente e iniciando o scheduler, o preflight deve falhar com mensagem acionavel e interromper o processo (SystemExit).
result: issue
reported: "iniciou e fechou"
severity: major

### 3. Preflight Warning Nao Critico
expected: Com variaveis criticas corretas e arquivo de Excel ausente, o preflight deve emitir warning nao critico e continuar o startup normalmente.
result: issue
reported: "nao consigo ver o erro a tempo, ele abre e fecha muito rapido"
severity: blocker

### 4. Idempotencia por Janela
expected: Acionando o mesmo job duas vezes na mesma janela de execucao, a segunda tentativa deve ser ignorada com evento de idempotent_skip, sem duplicar processamento.
result: issue
reported: "ainda nao consigo ver o erro"
severity: major

### 5. Isolamento de Falha por Item
expected: Se um item/jogo falhar durante processamento, o ciclo nao deve abortar por completo; os demais itens continuam e o ciclo pode ser marcado como degraded quando falha critica de persistencia ocorrer.
result: issue
reported: "PS C:\\Users\\Leo\\edge_protocol> python scheduler.py ... preflight failed: Schema minimo incompleto: job_execucoes"
severity: blocker

### 6. Logs Estruturados de Diagnostico
expected: Durante boot e ciclo, os logs devem incluir eventos estruturados para boot start/ready, preflight start/pass/fail, job guard start/skip/end e cycle_totals com contexto util para triagem diaria.
result: issue
reported: "python scheduler.py mostrou boot/preflight estruturados, mas preflight failed em Schema minimo incompleto: job_execucoes"
severity: blocker

## Summary

total: 6
passed: 0
issues: 6
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "O boot deve completar sem erro de inicializacao e sem traceback, entrando em modo ativo"
  status: failed
  reason: "User reported: iniciei e fechou"
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
  reason: "User reported: iniciou e fechou"
  severity: major
  test: 2
  root_cause: "Falha de schema ocorre antes da validacao de env vars, impedindo validar o comportamento especifico de BOT_TOKEN/CANAL_VIP."
  artifacts:
    - path: "scheduler.py"
      issue: "Falha de prerequisito de schema mascara teste de preflight de env"
  missing:
    - "Reordenar preflight para nao mascarar validacoes de env"
    - "Executar reteste de env apos corrigir bootstrap da tabela"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Com variaveis criticas corretas e Excel ausente, o preflight deve avisar e manter startup"
  status: failed
  reason: "User reported: nao consigo ver o erro a tempo, ele abre e fecha muito rapido"
  severity: blocker
  test: 3
  root_cause: "Erro critico de schema derruba processo antes do ramo de warning nao critico do Excel e antes de logs de ciclo."
  artifacts:
    - path: "scheduler.py"
      issue: "Preflight falha no schema e nao alcanca validacao nao-critica do Excel"
  missing:
    - "Corrigir bootstrap da tabela job_execucoes para destravar fluxo de warning nao-critico"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "A segunda execucao na mesma janela deve ser ignorada com idempotent_skip"
  status: failed
  reason: "User reported: ainda nao consigo ver o erro"
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
  reason: "User reported: PS C:\\Users\\Leo\\edge_protocol> python scheduler.py ... preflight failed: Schema minimo incompleto: job_execucoes"
  severity: blocker
  test: 5
  root_cause: "Nao foi possivel validar isolamento por item porque o ciclo nunca inicia; bloqueio ocorre no preflight de startup."
  artifacts:
    - path: "scheduler.py"
      issue: "Falha precoce impede entrar no loop de processamento por item"
  missing:
    - "Corrigir ordem de bootstrap/preflight"
    - "Reexecutar teste de isolamento apos startup funcional"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
- truth: "Logs estruturados devem cobrir boot/preflight e ciclo (job guard/cycle_totals) para diagnostico"
  status: failed
  reason: "User reported: python scheduler.py mostrou boot/preflight estruturados, mas preflight failed em Schema minimo incompleto: job_execucoes"
  severity: blocker
  test: 6
  root_cause: "Logs de boot/preflight estao presentes, mas logs de ciclo nao aparecem porque startup e interrompido no preflight."
  artifacts:
    - path: "scheduler.py"
      issue: "Interrupcao no preflight impede emissao de logs de job guard e cycle_totals"
  missing:
    - "Corrigir bloqueio de schema para permitir logs completos de ciclo"
  debug_session: ".planning/debug/03-preflight-schema-blocking.md"
