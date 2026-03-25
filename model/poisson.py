from scipy.stats import poisson
from scipy.optimize import minimize
import numpy as np
import math
import json
import os

# ── RHO POR LIGA (estimativas empíricas) ──────────────────────
RHO_POR_LIGA = {
    "Premier League":          0.00,
    "EPL":                     0.00,
    "La Liga":                -0.0075,
    "Serie A":                -0.0359,
    "Bundesliga":             -0.1120,
    "Ligue 1":                -0.0617,
    "UEFA Champions League":  -0.09,
    "UEFA Europa League":     -0.10,
    "Brasileirao Serie A":    -0.11,
    "Brazil Série A":         -0.11,
}
RHO_DEFAULT = -0.10
HOME_ADVANTAGE_DEFAULT = 1.0
CALIBRACAO_LIGAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "calibracao_ligas.json",
)

_calibracao_cache = None


def _reset_calibracao_cache():
    global _calibracao_cache
    _calibracao_cache = None


def _carregar_calibracao_ligas():
    global _calibracao_cache
    if _calibracao_cache is not None:
        return _calibracao_cache

    if not os.path.exists(CALIBRACAO_LIGAS_PATH):
        _calibracao_cache = {}
        return _calibracao_cache

    try:
        with open(CALIBRACAO_LIGAS_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        ligas = payload.get("ligas", {}) if isinstance(payload, dict) else {}
        _calibracao_cache = ligas if isinstance(ligas, dict) else {}
    except Exception:
        _calibracao_cache = {}

    return _calibracao_cache


def _resolver_rho_e_home_advantage(liga=None, rho=None):
    if rho is not None:
        return rho, HOME_ADVANTAGE_DEFAULT

    calibracao_ligas = _carregar_calibracao_ligas()
    if liga and liga in calibracao_ligas:
        cfg = calibracao_ligas.get(liga, {})
        rho_cfg = cfg.get("rho", RHO_DEFAULT)
        home_adv_cfg = cfg.get("home_advantage", HOME_ADVANTAGE_DEFAULT)
        try:
            rho_cfg = float(rho_cfg)
        except Exception:
            rho_cfg = RHO_DEFAULT
        try:
            home_adv_cfg = float(home_adv_cfg)
        except Exception:
            home_adv_cfg = HOME_ADVANTAGE_DEFAULT
        return rho_cfg, max(0.5, min(1.5, home_adv_cfg))

    if liga and liga in RHO_POR_LIGA:
        return RHO_POR_LIGA[liga], HOME_ADVANTAGE_DEFAULT

    return RHO_DEFAULT, HOME_ADVANTAGE_DEFAULT


def _matriz_probabilidades_dc(lambda_casa, lambda_fora, max_gols, rho):
    matriz = np.zeros((max_gols + 1, max_gols + 1))
    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p = (
                poisson.pmf(i, lambda_casa)
                * poisson.pmf(j, lambda_fora)
                * tau(i, j, lambda_casa, lambda_fora, rho)
            )
            matriz[i][j] = max(0.0, p)

    total = matriz.sum()
    if total > 0:
        matriz = matriz / total
    return matriz

# ── FUNÇÃO TAU (fator de correção Dixon-Coles) ────────────────
def tau(i, j, lambda_casa, lambda_fora, rho):
    """
    Fator de correção Dixon-Coles para placares baixos.
    Corrige a subestimação de 0x0/1x1 e superestimação de 1x0/0x1
    pelo modelo Poisson padrão.
    """
    if i == 0 and j == 0:
        return 1 - lambda_casa * lambda_fora * rho
    elif i == 1 and j == 0:
        return 1 + lambda_fora * rho
    elif i == 0 and j == 1:
        return 1 + lambda_casa * rho
    elif i == 1 and j == 1:
        return 1 - rho
    else:
        return 1.0

# ── ESTIMAÇÃO DE RHO POR MÁXIMA VEROSSIMILHANÇA ───────────────
def estimar_rho(dados_historicos):
    """
    Estima o parâmetro rho por máxima verossimilhança.

    dados_historicos: lista de dicts com keys 'gols_casa' e 'gols_fora'
    Retorna: float rho otimizado (entre -0.5 e 0.0)
    Fallback: RHO_DEFAULT se < 50 jogos disponíveis
    """
    if not dados_historicos or len(dados_historicos) < 50:
        return RHO_DEFAULT

    gols_casa_list = [d["gols_casa"] for d in dados_historicos]
    gols_fora_list = [d["gols_fora"] for d in dados_historicos]

    lambda_casa = np.mean(gols_casa_list)
    lambda_fora = np.mean(gols_fora_list)

    def neg_log_likelihood(params):
        rho_val = params[0]
        total = 0.0
        for gc, gf in zip(gols_casa_list, gols_fora_list):
            p = (poisson.pmf(gc, lambda_casa) *
                 poisson.pmf(gf, lambda_fora) *
                 tau(gc, gf, lambda_casa, lambda_fora, rho_val))
            if p <= 0:
                return 1e10
            total += math.log(p)
        return -total

    resultado = minimize(
        neg_log_likelihood,
        x0=[-0.10],
        method="L-BFGS-B",
        bounds=[(-0.5, 0.0)]
    )

    if resultado.success:
        return round(float(resultado.x[0]), 4)
    return RHO_DEFAULT

# ── MODELO POISSON COM CORREÇÃO DIXON-COLES ───────────────────
def calcular_probabilidades(media_gols_casa, media_gols_fora,
                             max_gols=6, liga=None, rho=None):
    """
    Modelo Poisson Bivariado com correção Dixon-Coles.

    Parâmetros:
        media_gols_casa  — xG esperado do time da casa
        media_gols_fora  — xG esperado do time visitante
        max_gols         — limite da matriz de placares (default 6)
        liga             — nome da liga para usar rho específico
        rho              — rho manual (sobrescreve liga e default)

    Retorna dict com:
        prob_casa, prob_empate, prob_fora  — com correção DC
        prob_casa_raw, prob_empate_raw, prob_fora_raw  — sem correção
        dc_delta_empate  — quanto a correção mudou o empate
        rho_usado        — valor de rho aplicado
    """
    rho_usado, home_advantage = _resolver_rho_e_home_advantage(liga=liga, rho=rho)

    lc = media_gols_casa * home_advantage
    lf = media_gols_fora

    # ── Poisson padrão (sem correção) ────────────────────────
    prob_casa_raw  = 0.0
    prob_empate_raw = 0.0
    prob_fora_raw  = 0.0

    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p = poisson.pmf(i, lc) * poisson.pmf(j, lf)
            if i > j:
                prob_casa_raw += p
            elif i == j:
                prob_empate_raw += p
            else:
                prob_fora_raw += p

    matriz = _matriz_probabilidades_dc(lc, lf, max_gols, rho_usado)

    # Soma por resultado
    prob_casa   = 0.0
    prob_empate = 0.0
    prob_fora   = 0.0

    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            if i > j:
                prob_casa += matriz[i][j]
            elif i == j:
                prob_empate += matriz[i][j]
            else:
                prob_fora += matriz[i][j]

    # Verifica soma ≈ 1.0
    soma = prob_casa + prob_empate + prob_fora
    assert abs(soma - 1.0) < 0.001, f"Soma das probs = {soma:.6f} (esperado ~1.0)"

    delta_empate = round((prob_empate - prob_empate_raw) * 100, 2)

    return {
        # Interface original mantida
        "prob_casa":   round(prob_casa, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_fora":   round(prob_fora, 4),
        # Campos novos
        "prob_casa_raw":   round(prob_casa_raw, 4),
        "prob_empate_raw": round(prob_empate_raw, 4),
        "prob_fora_raw":   round(prob_fora_raw, 4),
        "dc_delta_empate": delta_empate,
        "rho_usado":       rho_usado,
        "home_advantage_usado": round(home_advantage, 4),
    }

def calcular_prob_over_under(media_gols_casa, media_gols_fora,
                              linha=2.5, max_gols=10, liga=None, rho=None):
    """
    Calcula probabilidade de Over/Under para uma linha de gols.
    Usa soma bivariada (mais precisa que Poisson univariado).
    """
    rho_usado, home_advantage = _resolver_rho_e_home_advantage(liga=liga, rho=rho)
    lc = media_gols_casa * home_advantage
    lf = media_gols_fora
    matriz_dc = _matriz_probabilidades_dc(lc, lf, max_gols, rho_usado)
    prob_over = 0.0
    prob_under = 0.0
    prob_over_raw = 0.0
    prob_under_raw = 0.0

    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p_raw = poisson.pmf(i, lc) * poisson.pmf(j, lf)
            p = matriz_dc[i][j]
            if (i + j) > linha:
                prob_over += p
                prob_over_raw += p_raw
            else:
                prob_under += p
                prob_under_raw += p_raw

    soma = prob_over + prob_under
    assert abs(soma - 1.0) < 0.001, f"Soma over/under = {soma:.6f} (esperado ~1.0)"

    return {
        "prob_over":  round(prob_over, 4),
        "prob_under": round(prob_under, 4),
        "prob_over_raw": round(prob_over_raw, 4),
        "prob_under_raw": round(prob_under_raw, 4),
        "linha":      linha,
        "rho_usado": rho_usado,
        "home_advantage_usado": round(home_advantage, 4),
    }

def calcular_prob_btts(media_gols_casa, media_gols_fora):
    """
    Calcula probabilidade de Ambas Marcam (BTTS).
    """
    prob_casa_nao_marca = poisson.pmf(0, media_gols_casa)
    prob_fora_nao_marca = poisson.pmf(0, media_gols_fora)

    prob_btts_sim = (1 - prob_casa_nao_marca) * (1 - prob_fora_nao_marca)
    prob_btts_nao = 1 - prob_btts_sim

    return {
        "prob_btts_sim": round(prob_btts_sim, 4),
        "prob_btts_nao": round(prob_btts_nao, 4)
    }

def ajuste_contextual(prob, fator):
    """
    Ajusta uma probabilidade por um fator contextual.
    Fator positivo aumenta, negativo diminui.
    """
    nova_prob = prob + fator
    return round(max(0.01, min(0.99, nova_prob)), 4)

def log_comparacao(jogo, lc, lf, resultado):
    """
    Loga comparação antes/depois da correção Dixon-Coles.
    """
    print(f"\n[Dixon-Coles] {jogo}")
    print(f"  λ_casa={lc:.2f} | λ_fora={lf:.2f} | ρ={resultado['rho_usado']}")
    print(f"  {'Mercado':<12} {'Sem DC':>8} {'Com DC':>8} {'Delta':>8}")
    print(f"  {'Casa':<12} {resultado['prob_casa_raw']*100:>7.1f}% "
          f"{resultado['prob_casa']*100:>7.1f}% "
          f"{(resultado['prob_casa']-resultado['prob_casa_raw'])*100:>+7.1f}%")
    print(f"  {'Empate':<12} {resultado['prob_empate_raw']*100:>7.1f}% "
          f"{resultado['prob_empate']*100:>7.1f}% "
          f"{resultado['dc_delta_empate']:>+7.1f}%")
    print(f"  {'Fora':<12} {resultado['prob_fora_raw']*100:>7.1f}% "
          f"{resultado['prob_fora']*100:>7.1f}% "
          f"{(resultado['prob_fora']-resultado['prob_fora_raw'])*100:>+7.1f}%")

if __name__ == "__main__":
    print("=== TESTE DO MODELO POISSON + DIXON-COLES ===\n")

    casa = 1.8
    fora = 1.1

    # Teste sem liga (rho default -0.10)
    r = calcular_probabilidades(casa, fora)
    print(f"Médias: Casa={casa} | Fora={fora}")
    print(f"Vitória Casa:  {r['prob_casa']*100:.1f}%  (era {r['prob_casa_raw']*100:.1f}%)")
    print(f"Empate:        {r['prob_empate']*100:.1f}%  (era {r['prob_empate_raw']*100:.1f}%)")
    print(f"Vitória Fora:  {r['prob_fora']*100:.1f}%  (era {r['prob_fora_raw']*100:.1f}%)")
    print(f"ρ usado: {r['rho_usado']} | Δ empate: {r['dc_delta_empate']:+.2f}%")

    log_comparacao("Arsenal vs Chelsea", casa, fora, r)

    # Teste com liga específica
    print("\n--- Por liga ---")
    for liga, rho_l in RHO_POR_LIGA.items():
        r2 = calcular_probabilidades(1.5, 1.3, liga=liga)
        print(f"{liga:<28} ρ={r2['rho_usado']:>6} | "
              f"Empate: {r2['prob_empate_raw']*100:.1f}% → "
              f"{r2['prob_empate']*100:.1f}% "
              f"(Δ{r2['dc_delta_empate']:+.1f}%)")

    # Teste Over/Under
    over = calcular_prob_over_under(casa, fora, linha=2.5)
    print(f"\nOver 2.5:  {over['prob_over']*100:.1f}%")
    print(f"Under 2.5: {over['prob_under']*100:.1f}%")

    # Teste estimação rho
    print("\n--- Estimação rho com dados simulados ---")
    import random
    random.seed(42)
    historico = [{"gols_casa": random.randint(0,4),
                  "gols_fora": random.randint(0,3)}
                 for _ in range(200)]
    rho_estimado = estimar_rho(historico)
    print(f"ρ estimado com 200 jogos: {rho_estimado}")