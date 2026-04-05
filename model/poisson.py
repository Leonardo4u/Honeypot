from scipy.optimize import minimize
import numpy as np
import math
import json
import os

# -- RHO POR LIGA (estimativas empricas) ------------
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
    "Brazil Srie A":         -0.11,
}
RHO_DEFAULT = -0.10
HOME_ADVANTAGE_DEFAULT = 1.0
RHO_EXPECTED_RANGE = {
    "Bundesliga": (-0.15, -0.05),
    "La Liga": (-0.15, -0.05),
    "Serie A": (-0.15, -0.05),
    "Ligue 1": (-0.15, -0.05),
}
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
        with open(CALIBRACAO_LIGAS_PATH, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            # Compatibilidade: aceita tanto {"ligas": {...}} quanto {...} direto.
            ligas = payload.get("ligas", payload)
        else:
            ligas = {}
        _calibracao_cache = ligas if isinstance(ligas, dict) else {}
    except Exception:
        _calibracao_cache = {}

    return _calibracao_cache


def _resolver_rho_e_home_advantage(liga=None, rho=None):
    if rho is not None:
        return rho, HOME_ADVANTAGE_DEFAULT, None

    calibracao_ligas = _carregar_calibracao_ligas()
    if liga and liga in calibracao_ligas:
        cfg = calibracao_ligas.get(liga, {})
        rho_cfg = cfg.get("rho", RHO_DEFAULT)
        home_adv_cfg = cfg.get("home_advantage", HOME_ADVANTAGE_DEFAULT)
        # INTEGRATION: recency_halflife opcional por liga em calibracao_ligas.json.
        recency_halflife_cfg = cfg.get("recency_halflife", None)
        try:
            rho_cfg = float(rho_cfg)
        except Exception:
            rho_cfg = RHO_DEFAULT
        try:
            home_adv_cfg = float(home_adv_cfg)
        except Exception:
            home_adv_cfg = HOME_ADVANTAGE_DEFAULT
        try:
            recency_halflife_cfg = None if recency_halflife_cfg is None else float(recency_halflife_cfg)
        except Exception:
            recency_halflife_cfg = None
        return rho_cfg, max(0.5, min(1.5, home_adv_cfg)), recency_halflife_cfg

    if liga and liga in RHO_POR_LIGA:
        return RHO_POR_LIGA[liga], HOME_ADVANTAGE_DEFAULT, None

    return RHO_DEFAULT, HOME_ADVANTAGE_DEFAULT, None


def _build_recency_weights(n: int, recency_halflife=None):
    """Retorna pesos normalizados por recencia; None preserva comportamento igual-ponderado."""
    if n <= 0:
        return np.array([], dtype=float)
    if recency_halflife is None:
        return np.ones(n, dtype=float)

    try:
        halflife = float(recency_halflife)
    except Exception:
        return np.ones(n, dtype=float)
    if halflife <= 0:
        return np.ones(n, dtype=float)

    idx = np.arange(n, dtype=float)
    decay_rate = math.log(2.0) / halflife
    # INTEGRATION: ponderacao exponencial por recencia nas estimativas de lambda/rho.
    # i=0 mais antigo, i=n-1 mais recente.
    raw = np.exp(-decay_rate * ((n - 1) - idx))
    return raw


def _poisson_pmf(k, lam):
    """
    PMF de Poisson local para evitar dependncia de stubs externos em testes.
    """
    try:
        k_int = int(k)
        lam_v = float(lam)
    except Exception:
        return 0.0

    if k_int < 0 or not math.isfinite(lam_v):
        return 0.0
    if lam_v <= 0.0:
        return 1.0 if k_int == 0 else 0.0

    return math.exp(-lam_v) * (lam_v ** k_int) / math.factorial(k_int)


def _matriz_probabilidades_dc(lambda_casa, lambda_fora, max_gols, rho):
    matriz = np.zeros((max_gols + 1, max_gols + 1))
    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p = (
                _poisson_pmf(i, lambda_casa)
                * _poisson_pmf(j, lambda_fora)
                * tau(i, j, lambda_casa, lambda_fora, rho)
            )
            matriz[i][j] = max(0.0, p)

    total = matriz.sum()
    if total > 0:
        matriz = matriz / total
    return matriz


def _matriz_probabilidades_independente(lambda_casa, lambda_fora, max_gols):
    """Fallback sem correo Dixon-Coles quando a matriz DC colapsa."""
    matriz = np.zeros((max_gols + 1, max_gols + 1))
    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            matriz[i][j] = max(0.0, _poisson_pmf(i, lambda_casa) * _poisson_pmf(j, lambda_fora))
    total = matriz.sum()
    if total > 0:
        matriz = matriz / total
    return matriz


def _normalizar_probabilidades(par_a, par_b):
    soma = par_a + par_b
    if soma <= 0 or not math.isfinite(soma):
        return 0.5, 0.5
    return par_a / soma, par_b / soma


def _matriz_dc_robusta(lambda_casa, lambda_fora, max_gols, rho):
    """
    Tenta matriz DC e cai para matriz independente se houver soma invlida.
    Evita assert de soma=0 em cenrios extremos de rho/tau.
    """
    matriz = _matriz_probabilidades_dc(lambda_casa, lambda_fora, max_gols, rho)
    total = float(matriz.sum())
    if total > 0 and math.isfinite(total):
        return matriz
    return _matriz_probabilidades_independente(lambda_casa, lambda_fora, max_gols)

# -- FUNO TAU (fator de correo Dixon-Coles) ------------
def tau(i, j, lambda_casa, lambda_fora, rho):
    """
    Fator de correo Dixon-Coles para placares baixos.
    Corrige a subestimao de 0x0/1x1 e superestimao de 1x0/0x1
    pelo modelo Poisson padro.
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

# -- ESTIMAO DE RHO POR MXIMA VEROSSIMILHANA ------------
def estimar_rho(dados_historicos, recency_halflife=None, league_name=None, debug=False):
    """
    Estima o parmetro rho por mxima verossimilhana.

    dados_historicos: lista de dicts com keys 'gols_casa' e 'gols_fora'
    Retorna: float rho otimizado (entre -0.35 e -0.01)
    Fallback: RHO_DEFAULT se < 50 jogos disponveis
    """
    if not dados_historicos or len(dados_historicos) < 50:
        return RHO_DEFAULT

    gols_casa_list = [d["gols_casa"] for d in dados_historicos]
    gols_fora_list = [d["gols_fora"] for d in dados_historicos]

    weights = _build_recency_weights(len(dados_historicos), recency_halflife=recency_halflife)
    lambda_casa = float(np.average(gols_casa_list, weights=weights))
    lambda_fora = float(np.average(gols_fora_list, weights=weights))

    prior_center = -0.10
    prior_strength = 10.0

    def neg_log_likelihood(params):
        rho_val = params[0]
        total = 0.0
        for gc, gf, w_i in zip(gols_casa_list, gols_fora_list, weights):
            p = (_poisson_pmf(gc, lambda_casa) *
                 _poisson_pmf(gf, lambda_fora) *
                 tau(gc, gf, lambda_casa, lambda_fora, rho_val))
            if p <= 0:
                return 1e10
            total += float(w_i) * math.log(p)
        # Penalizacao fraca para evitar colapso em rho~=0 quando a superficie fica quase plana.
        reg = prior_strength * ((float(rho_val) - prior_center) ** 2)
        return -total + reg

    bounds = (-0.35, -0.01)
    grid = np.linspace(bounds[0], bounds[1], 41)
    best_grid = min(grid, key=lambda r: neg_log_likelihood([float(r)]))
    x0 = [float(best_grid)]

    resultado = minimize(
        neg_log_likelihood,
        x0=x0,
        method="L-BFGS-B",
        bounds=[bounds],
    )

    if resultado.success and np.isfinite(resultado.x[0]):
        rho_otimo = float(resultado.x[0])
    elif np.isfinite(best_grid):
        rho_otimo = float(best_grid)
    else:
        rho_otimo = RHO_DEFAULT

    if debug:
        liga_label = league_name or "liga_desconhecida"
        converged = "yes" if resultado.success else "no"
        nit = getattr(resultado, "nit", 0)
        print(
            f"[RHO_OPT] liga={liga_label} converged={converged} "
            f"rho={rho_otimo:.4f} iterations={int(nit)} x0={float(x0[0]):.4f}"
        )

    if abs(rho_otimo - float(x0[0])) <= 1e-8 and debug:
        liga_label = league_name or "liga_desconhecida"
        print(
            f"[WARN] RHO optimizer stayed at initial value for {liga_label}: "
            f"rho={rho_otimo:.4f}. Check data quality and low-score likelihood signal."
        )

    if debug and (abs(rho_otimo - bounds[1]) <= 1e-4 or abs(rho_otimo - bounds[0]) <= 1e-4):
        liga_label = league_name or "liga_desconhecida"
        print(
            f"[WARN] RHO optimizer hit bound for {liga_label}: rho={rho_otimo:.4f} "
            f"bounds=({bounds[0]:.2f},{bounds[1]:.2f})"
        )

    if league_name in RHO_EXPECTED_RANGE:
        lo, hi = RHO_EXPECTED_RANGE[league_name]
        rho_clamped = min(max(rho_otimo, lo), hi)
        if debug and abs(rho_clamped - rho_otimo) > 1e-8:
            print(
                f"[WARN] RHO clamped for {league_name}: raw={rho_otimo:.4f} -> clamped={rho_clamped:.4f} "
                f"range=[{lo:.2f},{hi:.2f}]"
            )
        rho_otimo = rho_clamped

    return round(float(rho_otimo), 4)

# -- MODELO POISSON COM CORREO DIXON-COLES ------------
def calcular_probabilidades(media_gols_casa, media_gols_fora,
                             max_gols=6, liga=None, rho=None):
    """
    Modelo Poisson Bivariado com correo Dixon-Coles.

    Parmetros:
        media_gols_casa   xG esperado do time da casa
        media_gols_fora   xG esperado do time visitante
        max_gols          limite da matriz de placares (default 6)
        liga              nome da liga para usar rho especfico
        rho               rho manual (sobrescreve liga e default)

    Retorna dict com:
        prob_casa, prob_empate, prob_fora   com correo DC
        prob_casa_raw, prob_empate_raw, prob_fora_raw   sem correo
        dc_delta_empate   quanto a correo mudou o empate
        rho_usado         valor de rho aplicado
    """
    rho_usado, home_advantage, recency_halflife = _resolver_rho_e_home_advantage(liga=liga, rho=rho)

    lc = media_gols_casa * home_advantage
    lf = media_gols_fora

    # -- Poisson padro (sem correo) ------------
    prob_casa_raw  = 0.0
    prob_empate_raw = 0.0
    prob_fora_raw  = 0.0

    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p = _poisson_pmf(i, lc) * _poisson_pmf(j, lf)
            if i > j:
                prob_casa_raw += p
            elif i == j:
                prob_empate_raw += p
            else:
                prob_fora_raw += p

    matriz = _matriz_dc_robusta(lc, lf, max_gols, rho_usado)

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

    # Verifica soma  1.0
    soma = prob_casa + prob_empate + prob_fora
    if soma > 0 and math.isfinite(soma):
        prob_casa /= soma
        prob_empate /= soma
        prob_fora /= soma
    else:
        prob_casa, prob_empate, prob_fora = 1 / 3, 1 / 3, 1 / 3

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
        "recency_halflife_usado": recency_halflife,
    }

def calcular_prob_over_under(media_gols_casa, media_gols_fora,
                              linha=2.5, max_gols=10, liga=None, rho=None):
    """
    Calcula probabilidade de Over/Under para uma linha de gols.
    Usa soma bivariada (mais precisa que Poisson univariado).
    """
    rho_usado, home_advantage, recency_halflife = _resolver_rho_e_home_advantage(liga=liga, rho=rho)
    lc = media_gols_casa * home_advantage
    lf = media_gols_fora
    matriz_dc = _matriz_dc_robusta(lc, lf, max_gols, rho_usado)
    prob_over = 0.0
    prob_under = 0.0
    prob_over_raw = 0.0
    prob_under_raw = 0.0

    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p_raw = _poisson_pmf(i, lc) * _poisson_pmf(j, lf)
            p = matriz_dc[i][j]
            if (i + j) > linha:
                prob_over += p
                prob_over_raw += p_raw
            else:
                prob_under += p
                prob_under_raw += p_raw

    prob_over, prob_under = _normalizar_probabilidades(prob_over, prob_under)
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
        "recency_halflife_usado": recency_halflife,
    }

def calcular_prob_btts(media_gols_casa, media_gols_fora):
    """
    Calcula probabilidade de Ambas Marcam (BTTS).
    """
    prob_casa_nao_marca = _poisson_pmf(0, media_gols_casa)
    prob_fora_nao_marca = _poisson_pmf(0, media_gols_fora)

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
    Loga comparao antes/depois da correo Dixon-Coles.
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

    # Teste com liga especfica
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

    # Teste estimao rho
    print("\n--- Estimao rho com dados simulados ---")
    import random
    random.seed(42)
    historico = [{"gols_casa": random.randint(0,4),
                  "gols_fora": random.randint(0,3)}
                 for _ in range(200)]
    rho_estimado = estimar_rho(historico)
    print(f"ρ estimado com 200 jogos: {rho_estimado}")