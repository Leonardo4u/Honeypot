import math


MIN_CONFIDENCE_ACTIONABLE = 64.0


def calcular_ev(prob_estimada, odd):
    """
    Calcula o Expected Value (EV) de uma aposta.
    EV positivo = aposta com valor real.
    EV = (probabilidade  odd) - 1
    """
    ev = (prob_estimada * odd) - 1
    return round(ev, 4)

def odd_para_prob(odd):
    """
    Converte odd decimal para probabilidade implcita (com vig).
    """
    return round(1 / odd, 4)

def calcular_edge_score(ev, confianca_dados, estabilidade_odd, contexto_jogo):
    """
    Calcula o EDGE Score final (0-100).

    Parmetros (todos de 0 a 100):
    - ev:               baseado no EV calculado
    - confianca_dados:  qualidade dos dados disponveis
    - estabilidade_odd: odd estvel nas ltimas horas
    - contexto_jogo:    motivao, importncia, fadiga

    Pesos:
    - EV:               40%
    - Confiana dados:  25%
    - Estabilidade odd: 20%
    - Contexto jogo:    15%
    """
    score = (
        (ev * 0.40) +
        (confianca_dados * 0.25) +
        (estabilidade_odd * 0.20) +
        (contexto_jogo * 0.15)
    )
    return round(min(100, max(0, score)), 1)

def ev_para_score(ev):
    """
    Converte EV decimal para score de 0-100.
    EV de 0.04 (4%) = score 50 (mnimo aceitvel)
    EV de 0.12 (12%) = score 100
    """
    if ev <= 0:
        return 0
    score = (ev / 0.12) * 100
    return round(min(100, score), 1)

def calcular_stake(edge_score, banca_atual, unidade_percentual=0.01):
    """
    Calcula o valor da stake baseado no EDGE Score.
    Score 80+: 3 unidades
    Score 65-79: 2 unidades
    Score 50-64: 1 unidade (opcional, no enviar sinal)
    """
    unidade = banca_atual * unidade_percentual

    if edge_score >= 80:
        unidades = 3
    elif edge_score >= 65:
        unidades = 2
    elif edge_score >= 50:
        unidades = 1
    else:
        unidades = 0

    return {
        "unidades": unidades,
        "valor_reais": round(unidade * unidades, 2),
        "unidade_valor": round(unidade, 2)
    }

def decisao_sinal(edge_score):
    """
    Retorna a deciso final baseada no EDGE Score.
    """
    if edge_score >= 80:
        return "PREMIUM"
    elif edge_score >= 65:
        return "PADRAO"
    elif edge_score >= 50:
        return "WATCHLIST"
    else:
        return "DESCARTAR"


def calcular_kelly_fracionado(prob_modelo, odd, fracao=0.25, teto=0.05):
    """
    Calcula Kelly fracionado em escala 0-1.
    Campo auxiliar para tornar a sada diretamente acionvel,
    sem substituir o mdulo principal de banca.
    """
    try:
        p = float(prob_modelo)
        o = float(odd)
        f = float(fracao)
        cap = float(teto)
    except (TypeError, ValueError):
        return 0.0

    if o <= 1.0 or p <= 0.0 or p >= 1.0 or f <= 0.0:
        return 0.0

    b = o - 1.0
    k_full = (p * o - 1.0) / b
    if not math.isfinite(k_full) or k_full <= 0.0:
        return 0.0

    return round(min(max(0.0, k_full * f), cap), 4)


def classificar_recomendacao(edge_score, confianca, ev, min_conf=MIN_CONFIDENCE_ACTIONABLE):
    """
    Classificao assertiva para consumo operacional.
    Mantm decisao_sinal legado intacto e adiciona rtulo BET/SKIP/AVOID.
    """
    try:
        es = float(edge_score or 0.0)
        cf = float(confianca or 0.0)
        ev_v = float(ev or 0.0)
        floor = float(min_conf)
    except (TypeError, ValueError):
        return "AVOID"

    if ev_v <= 0 or cf < (floor - 8.0):
        return "AVOID"
    if es >= 80.0 and cf >= floor and ev_v >= 0.02:
        return "BET"
    return "SKIP"


def montar_reasoning_trace(*, mercado, odd, prob_modelo, prob_implicita, ev, edge_score, confianca, min_conf):
    """
    Explica por que o sinal foi aceito/bloqueado e quais critrios pesaram.
    """
    fatores = [
        f"mercado={mercado}",
        f"odd={float(odd):.3f}",
        f"prob_modelo={float(prob_modelo):.4f}",
        f"prob_implicita={float(prob_implicita):.4f}",
        f"ev={float(ev):.4f}",
        f"edge_score={float(edge_score):.1f}",
        f"confianca={float(confianca):.2f}",
        f"min_conf={float(min_conf):.2f}",
    ]

    descartados = []
    if float(confianca) < float(min_conf):
        descartados.append("confianca_abaixo_cutoff")
    if float(ev) <= 0:
        descartados.append("ev_nao_positivo")
    if float(edge_score) < 65.0:
        descartados.append("edge_score_fraco")

    justificativa = (
        "Confiana e EV dentro do mnimo operacional"
        if float(confianca) >= float(min_conf) and float(ev) > 0
        else "Confiana/EV insuficientes para ao"
    )

    return {
        "fatores_utilizados": fatores,
        "fatores_descartados": descartados,
        "justificativa": justificativa,
    }

if __name__ == "__main__":
    print("=== TESTE DO EDGE SCORE ===\n")

    prob_modelo = 0.61
    odd_casa = 1.92
    banca = 1000

    ev = calcular_ev(prob_modelo, odd_casa)
    prob_implicita = odd_para_prob(odd_casa)

    print(f"Probabilidade do modelo: {prob_modelo*100:.1f}%")
    print(f"Probabilidade implícita da odd: {prob_implicita*100:.1f}%")
    print(f"Odd: {odd_casa}")
    print(f"EV calculado: {ev*100:.2f}%")

    ev_score = ev_para_score(ev)
    confianca = 80
    estabilidade = 75
    contexto = 70

    score = calcular_edge_score(ev_score, confianca, estabilidade, contexto)
    decisao = decisao_sinal(score)
    stake = calcular_stake(score, banca)

    print(f"\nEV Score:          {ev_score}/100")
    print(f"Confiança dados:   {confianca}/100")
    print(f"Estabilidade odd:  {estabilidade}/100")
    print(f"Contexto jogo:     {contexto}/100")
    print(f"\nEDGE Score Final:  {score}/100")
    print(f"Decisão:           {decisao}")
    print(f"\nBanca: R${banca:.2f}")
    print(f"Unidade: R${stake['unidade_valor']:.2f}")
    print(f"Stake: {stake['unidades']} unidades = R${stake['valor_reais']:.2f}")