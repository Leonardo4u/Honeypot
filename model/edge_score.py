def calcular_ev(prob_estimada, odd):
    """
    Calcula o Expected Value (EV) de uma aposta.
    EV positivo = aposta com valor real.
    EV = (probabilidade × odd) - 1
    """
    ev = (prob_estimada * odd) - 1
    return round(ev, 4)

def odd_para_prob(odd):
    """
    Converte odd decimal para probabilidade implícita (com vig).
    """
    return round(1 / odd, 4)

def calcular_edge_score(ev, confianca_dados, estabilidade_odd, contexto_jogo):
    """
    Calcula o EDGE Score final (0-100).

    Parâmetros (todos de 0 a 100):
    - ev:               baseado no EV calculado
    - confianca_dados:  qualidade dos dados disponíveis
    - estabilidade_odd: odd estável nas últimas horas
    - contexto_jogo:    motivação, importância, fadiga

    Pesos:
    - EV:               40%
    - Confiança dados:  25%
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
    EV de 0.04 (4%) = score 50 (mínimo aceitável)
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
    Score 50-64: 1 unidade (opcional, não enviar sinal)
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
    Retorna a decisão final baseada no EDGE Score.
    """
    if edge_score >= 80:
        return "PREMIUM"
    elif edge_score >= 65:
        return "PADRAO"
    elif edge_score >= 50:
        return "WATCHLIST"
    else:
        return "DESCARTAR"

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