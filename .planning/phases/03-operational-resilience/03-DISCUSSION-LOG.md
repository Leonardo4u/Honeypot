# Phase 3: Operational Resilience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 03-operational-resilience
**Areas discussed:** Idempotencia de jobs, isolamento de falhas, logging estruturado, preflight de startup

---

## Idempotencia de jobs e janelas

| Option | Description | Selected |
|--------|-------------|----------|
| Chave por janela + tipo de job em SQLite | Evita duplicidade com auditoria persistente e baixo custo operacional | x |
| Apenas lock em memoria por processo | Simples, mas falha em restart e nao protege sobreposicao externa | |
| Deduplicacao apenas por heuristica de horario | Fraca contra corridas e reexecucoes rapidas | |

**User's choice:** Defina o que for melhor para minha aplicacao, com foco em maior assertividade das apostas.
**Resolved as:** Chave por janela + tipo de job persistida em SQLite (opcao recomendada).
**Notes:** Decisao orientada a impedir execucoes duplicadas que distorcem sinais e resultado operacional.

---

## Isolamento de falhas por criticidade

| Option | Description | Selected |
|--------|-------------|----------|
| Isolar por jogo e degradar ciclo em falhas criticas | Mantem lote vivo, mas nao oculta falha de integridade | x |
| Falha global ao primeiro erro | Alta seguranca, baixa disponibilidade operacional | |
| Ignorar falhas amplamente e seguir | Alta disponibilidade, baixo controle de qualidade | |

**User's choice:** Defina o que for melhor para minha aplicacao, com foco em maior assertividade das apostas.
**Resolved as:** Isolamento por jogo com degradacao explicita para falhas criticas (opcao recomendada).
**Notes:** Preserva continuidade sem sacrificar confiabilidade dos dados.

---

## Logging operacional estruturado

| Option | Description | Selected |
|--------|-------------|----------|
| Manter print com formato estruturado estavel | Ganho alto de diagnostico com mudanca incremental | x |
| Trocar para framework completo de logging agora | Melhor escalabilidade, mas mais escopo e risco imediato | |
| Continuar com logs livres atuais | Menor esforco, baixa rastreabilidade | |

**User's choice:** Defina o que for melhor para minha aplicacao, com foco em maior assertividade das apostas.
**Resolved as:** Print estruturado com campos obrigatorios e marcos de ciclo (opcao recomendada).
**Notes:** Aumenta observabilidade sem expandir escopo da fase.

---

## Preflight de startup (fail-fast)

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-fast para criticos + warning para nao criticos | Evita subir quebrado e mantem operacao essencial | x |
| Apenas warnings para tudo | Menos bloqueio, maior risco de falha em runtime | |
| Fail-fast para tudo | Muito seguro, mas pode bloquear operacao por itens secundarios | |

**User's choice:** Defina o que for melhor para minha aplicacao, com foco em maior assertividade das apostas.
**Resolved as:** Fail-fast para criticos e warning para nao criticos (opcao recomendada).
**Notes:** Equilibrio entre seguranca operacional e continuidade.

---

## the agent's Discretion

- Detalhamento de schema e utilitarios de idempotencia no SQLite.
- Estrutura exata dos campos de log, mantendo consistencia de diagnostico.

## Deferred Ideas

- Refatoracao arquitetural ampla para multiplos workers/processos.
- Recursos de produto fora do escopo operacional da fase 3.
