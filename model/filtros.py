def gate1_ev_e_odd(ev, odd, mercado=""):
    ev_minimo = {
        "1x2_casa":  0.06,
        "over_2.5":  0.06,
    }

    minimo = ev_minimo.get(mercado, 0.06)

    if ev < minimo:
        return False, f"EV insuficiente: {ev*100:.2f}% (mínimo {minimo*100:.0f}% para {mercado})"
    if odd < 1.55:
        return False, f"Odd muito baixa: {odd} (mínimo 1.55)"
    if odd > 3.50:
        return False, f"Odd muito alta: {odd} (máximo 3.50)"
    return True, "OK"

def gate2_escalacao(escalacao_confirmada):
    if not escalacao_confirmada:
        return False, "Escalação não confirmada"
    return True, "OK"

def gate3_odd_estavel(variacao_odd_percentual):
    if variacao_odd_percentual < -8:
        return False, f"Steam negativo detectado: {variacao_odd_percentual:.1f}%"
    return True, "OK"

def gate4_limite_diario(sinais_hoje, max_sinais=10):
    if sinais_hoje >= max_sinais:
        return False, f"Limite diário atingido: {sinais_hoje}/{max_sinais}"
    return True, "OK"

def aplicar_triple_gate(dados_sinal, sinais_hoje=0):
    resultados = {}

    ok, msg = gate1_ev_e_odd(
        dados_sinal["ev"],
        dados_sinal["odd"],
        dados_sinal.get("mercado", "")
    )
    resultados["gate1"] = {"passou": ok, "msg": msg}
    if not ok:
        return {"aprovado": False, "bloqueado_em": "Gate 1", "motivo": msg, "detalhes": resultados}

    ok, msg = gate2_escalacao(dados_sinal.get("escalacao_confirmada", False))
    resultados["gate2"] = {"passou": ok, "msg": msg}
    if not ok:
        return {"aprovado": False, "bloqueado_em": "Gate 2", "motivo": msg, "detalhes": resultados}

    ok, msg = gate3_odd_estavel(dados_sinal.get("variacao_odd", 0))
    resultados["gate3"] = {"passou": ok, "msg": msg}
    if not ok:
        return {"aprovado": False, "bloqueado_em": "Gate 3", "motivo": msg, "detalhes": resultados}

    ok, msg = gate4_limite_diario(sinais_hoje)
    resultados["gate4"] = {"passou": ok, "msg": msg}
    if not ok:
        return {"aprovado": False, "bloqueado_em": "Gate 4", "motivo": msg, "detalhes": resultados}

    return {"aprovado": True, "bloqueado_em": None, "motivo": "Passou em todos os filtros", "detalhes": resultados}

if __name__ == "__main__":
    print("=== TESTE DO TRIPLE GATE FILTER ===\n")

    casos = [
        {"nome": "Over 2.5 ideal", "ev": 0.08, "odd": 1.92, "mercado": "over_2.5", "escalacao_confirmada": True, "variacao_odd": 0.0},
        {"nome": "Over 2.5 EV baixo", "ev": 0.04, "odd": 1.92, "mercado": "over_2.5", "escalacao_confirmada": True, "variacao_odd": 0.0},
        {"nome": "1x2 casa ideal", "ev": 0.07, "odd": 2.10, "mercado": "1x2_casa", "escalacao_confirmada": True, "variacao_odd": 0.0},
        {"nome": "Odd muito baixa", "ev": 0.08, "odd": 1.40, "mercado": "1x2_casa", "escalacao_confirmada": True, "variacao_odd": 0.0},
        {"nome": "Steam negativo", "ev": 0.08, "odd": 1.85, "mercado": "over_2.5", "escalacao_confirmada": True, "variacao_odd": -12.0},
    ]

    for caso in casos:
        nome = caso.pop("nome")
        resultado = aplicar_triple_gate(caso)
        status = "APROVADO" if resultado["aprovado"] else f"BLOQUEADO ({resultado['bloqueado_em']})"
        print(f"{nome}: {status}")
        if not resultado["aprovado"]:
            print(f"   Motivo: {resultado['motivo']}")
        print()