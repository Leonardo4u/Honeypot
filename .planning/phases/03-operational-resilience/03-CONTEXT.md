# Phase 3: Operational Resilience - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Fortalecer a execucao continua do scheduler para evitar duplicidade de processamento, isolar falhas por unidade de trabalho, melhorar diagnostico operacional e validar pre-requisitos criticos antes de iniciar loops.

Esta fase nao adiciona novas funcionalidades de produto; ela aumenta robustez operacional para proteger a qualidade e a assertividade das apostas.

</domain>

<decisions>
## Implementation Decisions

### Idempotencia de jobs e janelas
- **D-01:** Implementar idempotencia por janela de execucao com chave estavel por job (`analise`, `verificacao`, `resumo`, `clv`, `steam`) e data/hora-alvo, persistida em SQLite.
- **D-02:** Antes de executar cada job, verificar e registrar lock/logica de execucao para impedir reprocessamento em chamadas sobrepostas ou reinicios proximos.
- **D-03:** Tratar reexecucao da mesma janela como no-op com log explicito de skip idempotente.

### Isolamento de falhas por criticidade
- **D-04:** Falhas por jogo/fixture nunca devem abortar o lote; devem ser registradas com contexto e o loop segue para os demais itens.
- **D-05:** Falhas de persistencia critica (ex.: gravacao principal em DB) marcam o ciclo como degradado com alerta forte, sem mascaramento silencioso.
- **D-06:** Side effects secundarios (Excel, reacao Telegram, enriquecimentos) permanecem best-effort, mas com categoria de erro estruturada para auditoria.

### Logging operacional estruturado
- **D-07:** Manter logging via console, mas padronizar eventos em formato estruturado estavel contendo: categoria, etapa, entidade, status, reason_code e detalhes.
- **D-08:** Definir marcos obrigatorios de ciclo (inicio/fim de job, totais processados, skips idempotentes, falhas criticas e degradacao) para diagnostico diario rapido.

### Preflight de startup (fail-fast)
- **D-09:** Bloquear startup quando pre-requisitos criticos faltarem: `BOT_TOKEN`, canais obrigatorios, arquivo de banco e schema minimo esperado.
- **D-10:** Dependencias nao criticas devem gerar warning nao bloqueante com orientacao clara, sem impedir o scheduler principal.
- **D-11:** Preflight deve emitir relatorio unico de saude no boot para confirmar pronto para operar antes do primeiro ciclo.

### the agent's Discretion
- Escolha da representacao de chave idempotente (tabela dedicada ou reaproveitamento controlado em schema existente) desde que preserve auditoria e baixa complexidade.
- Nivel de detalhe dos campos de log estruturado, desde que mantenha consistencia para grep e comparacao entre ciclos.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap e escopo
- `.planning/ROADMAP.md` - Define o objetivo da Fase 3, requisitos OPS-01..OPS-04 e criterios de sucesso.

### Requisitos funcionais
- `.planning/REQUIREMENTS.md` - Fonte oficial dos requisitos de resiliencia operacional e rastreabilidade de conclusao.

### Contexto de produto
- `.planning/PROJECT.md` - Define prioridade de assertividade das apostas e restricoes de operacao single-operator.

### Padrões atuais de codigo
- `.planning/codebase/ARCHITECTURE.md` - Mostra fluxo orquestrado atual centrado em scheduler e pontos de fragilidade.
- `.planning/codebase/CONVENTIONS.md` - Padroes de logging, naming e tratamento de erro esperados no repositorio.
- `.planning/codebase/CONCERNS.md` - Riscos conhecidos de resiliencia que devem ser tratados sem ampliar escopo.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scheduler.py`: ponto unico de orquestracao onde entram controle de janelas, isolamento por job e marcos de log.
- `data/database.py`: base natural para helper(s) de controle idempotente e validacao de schema.
- `data/ingestion_resilience.py`: padrao recente de classificacao de erro reaproveitavel para logs estruturados.

### Established Patterns
- Fluxo script-first com loops agendados em `schedule` e wrappers `rodar_*` para cada job.
- Uso atual de `try/except` local com continuidade de processamento; fase 3 deve tornar isso explicito por criticidade.
- Persistencia em SQLite com funcoes utilitarias isoladas por modulo, sem framework pesado.

### Integration Points
- Boot path: `iniciar_scheduler()` em `scheduler.py` para preflight e relatorio de saude inicial.
- Execucao de jobs: funcoes `rodar_analise`, `rodar_verificacao`, `rodar_resumo`, `rodar_clv`, `rodar_steam`.
- Persistencia e estado operacional: `data/database.py` e `data/edge_protocol.db`.

</code_context>

<specifics>
## Specific Ideas

- Priorizar confiabilidade que impacta diretamente assertividade de aposta: evitar duplicidade, garantir integridade de ciclo e reduzir falha silenciosa.
- Optar por solucoes simples e auditaveis antes de qualquer refatoracao ampla de arquitetura.

</specifics>

<deferred>
## Deferred Ideas

- Refatoracao arquitetural grande do scheduler em multiplos servicos/processos.
- Mudancas de produto (novos mercados, UX/UI, recursos de bot fora de resiliencia operacional).

</deferred>

---

*Phase: 03-operational-resilience*
*Context gathered: 2026-03-24*
