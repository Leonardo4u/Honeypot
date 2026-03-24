# Testing Patterns

**Analysis Date:** 2026-03-24

## Test Framework

**Runner:**
- Framework: Not detected (no `pytest`, `unittest`, or dedicated test config files found).
- Config: Not applicable.

**Assertion Library:**
- Built-in Python `assert` for targeted invariants.
- Evidence: probability sum assertion in `model/poisson.py`.

**Run Commands:**
```bash
python model/poisson.py              # Validate Poisson + Dixon-Coles calculations
python model/edge_score.py           # Validate EV/score/stake logic
python model/filtros.py              # Validate triple-gate filtering logic
python model/analisar_jogo.py        # End-to-end analysis simulation
python testar_resultado.py           # Manual result lookup checks
python verificar_jogos_hoje.py       # Manual fixture/odds window checks
python criar_tabelas.py              # Initialize validation/bank tables
python main.py                       # Async end-to-end signal flow simulation
```

## Test File Organization

**Location:**
- Pattern: script-based tests are mixed with runtime modules and root utilities (co-located manual executable checks).
- Evidence: `model/poisson.py`, `model/edge_score.py`, `model/filtros.py`, `model/analisar_jogo.py`, `testar_resultado.py`, `verificar_jogos_hoje.py`.

**Naming:**
- Pattern: no `test_*.py` naming convention; test-like scripts use domain names (`debug_*.py`, `testar_*.py`) and `if __name__ == "__main__":` blocks.

**Structure:**
```
project-root/
├── model/*.py                 # Core logic with self-test blocks
├── data/*.py                  # Data/services with manual runtime checks
├── debug_*.py                 # Exploratory debugging scripts
├── testar_resultado.py        # Manual verification script
└── verificar_jogos_hoje.py    # Manual verification script
```

## Test Structure

**Suite Organization:**
```python
if __name__ == "__main__":
    print("=== TESTE ... ===")
    # build sample payloads
    # call target functions
    # print outcomes for manual validation
```

**Patterns:**
- Setup pattern: prepare inline dictionaries/lists with realistic match and odds data.
- Teardown pattern: not standardized (scripts terminate naturally).
- Assertion pattern: mostly visual/manual result inspection, with occasional strict assertions.
- Evidence: inline test payload in `model/analisar_jogo.py`; explicit assertion in `model/poisson.py`; output-driven checks in `model/edge_score.py` and `testar_resultado.py`.

## Mocking

**Framework:** Not detected.

**Patterns:**
```python
def _dados_simulados():
    return [{
        "id": "sim_001",
        "sport_title": "Premier League",
        ...
    }]
```

**What to Mock:**
- External APIs and services by fallback sample data.
- Evidence: `_dados_simulados()` in `data/coletar_odds.py` when `ODDS_API_KEY` is unavailable.

**What NOT to Mock:**
- Core probability/risk calculations in `model/` (validated with direct function execution).

## Fixtures and Factories

**Test Data:**
```python
jogo_teste = {
    "liga": "Premier League",
    "jogo": "Arsenal vs Chelsea",
    "mercado": "1x2_casa",
    "odd": 1.92,
    ...
}
resultado = analisar_jogo(jogo_teste)
```

**Location:**
- Inline fixtures inside executable module blocks.
- Evidence: `jogo_teste` in `model/analisar_jogo.py`; `casos` list in `model/filtros.py`; simulated history in `model/poisson.py`.

## Coverage

**Requirements:** None enforced (no coverage config or thresholds detected).

**View Coverage:**
```bash
Not applicable (coverage tooling not configured).
```

## Test Types

**Unit Tests:**
- Scope: function-level validation of mathematical and gating logic via direct execution scripts.
- Approach: deterministic inputs, printed outputs, occasional assertion guards.
- Evidence: `model/edge_score.py`, `model/filtros.py`, `model/poisson.py`.

**Integration Tests:**
- Scope: API/database/Telegram-connected flow checks.
- Approach: run orchestration scripts against configured environment variables and local DB.
- Evidence: `main.py`, `scheduler.py`, `testar_resultado.py`, `data/verificar_resultados.py`.

**E2E Tests:**
- Framework: Not used.
- Current equivalent: operational dry-runs through `main.py` and scheduler jobs in `scheduler.py`.

## Common Patterns

**Async Testing:**
```python
async def teste_completo():
    sinal_id = await enviar_sinal(jogo, publicar_free=False)

if __name__ == "__main__":
    asyncio.run(teste_completo())
```

**Error Testing:**
```python
try:
    response = requests.get(url, params=params, timeout=10)
except Exception as e:
    print(f"Erro de conexão: {e}")
    return []
```

---

*Testing analysis: 2026-03-24*
