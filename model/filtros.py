from signal_policy import (
    ODD_MAX,
    ODD_MIN,
    REJECT_CODE_DAILY_LIMIT,
    REJECT_CODE_LINEUP_UNCONFIRMED,
    REJECT_CODE_PASSED,
    REJECT_CODE_STEAM_NEGATIVE,
    REJECT_REASON_CODES,
    build_reject,
    get_market_ev_min,
)


def gate1_ev_e_odd(ev, odd, mercado=""):
    minimo = get_market_ev_min(mercado)

    if ev < minimo:
        return (
            False,
            f"EV insuficiente: {ev*100:.2f}% (mínimo {minimo*100:.0f}% para {mercado})",
            REJECT_REASON_CODES["gate1_ev"],
        )
    if odd < ODD_MIN:
        return False, f"Odd muito baixa: {odd} (mínimo {ODD_MIN})", REJECT_REASON_CODES["gate1_odd_low"]
    if odd > ODD_MAX:
        return False, f"Odd muito alta: {odd} (máximo {ODD_MAX})", REJECT_REASON_CODES["gate1_odd_high"]
    return True, "OK", None

def gate2_escalacao(escalacao_confirmada):
    if not escalacao_confirmada:
        return False, "Escalação não confirmada", REJECT_CODE_LINEUP_UNCONFIRMED
    return True, "OK", None

def gate3_odd_estavel(variacao_odd_percentual):
    if variacao_odd_percentual < -8:
        return False, f"Steam negativo detectado: {variacao_odd_percentual:.1f}%", REJECT_CODE_STEAM_NEGATIVE
    return True, "OK", None

def gate4_limite_diario(sinais_hoje, max_sinais=10):
    if sinais_hoje >= max_sinais:
        return False, f"Limite diário atingido: {sinais_hoje}/{max_sinais}", REJECT_CODE_DAILY_LIMIT
    return True, "OK", None

def aplicar_triple_gate(dados_sinal, sinais_hoje=0):
    resultados = {}

    ok, msg, reason_code = gate1_ev_e_odd(
        dados_sinal["ev"],
        dados_sinal["odd"],
        dados_sinal.get("mercado", "")
    )
    resultados["gate1"] = {"passou": ok, "msg": msg, "reason_code": reason_code}
    if not ok:
        return {"aprovado": False, **build_reject(reason_code, msg, "Gate 1", resultados)}

    ok, msg, reason_code = gate2_escalacao(dados_sinal.get("escalacao_confirmada", False))
    resultados["gate2"] = {"passou": ok, "msg": msg, "reason_code": reason_code}
    if not ok:
        return {"aprovado": False, **build_reject(reason_code, msg, "Gate 2", resultados)}

    ok, msg, reason_code = gate3_odd_estavel(dados_sinal.get("variacao_odd", 0))
    resultados["gate3"] = {"passou": ok, "msg": msg, "reason_code": reason_code}
    if not ok:
        return {"aprovado": False, **build_reject(reason_code, msg, "Gate 3", resultados)}

    ok, msg, reason_code = gate4_limite_diario(sinais_hoje)
    resultados["gate4"] = {"passou": ok, "msg": msg, "reason_code": reason_code}
    if not ok:
        return {"aprovado": False, **build_reject(reason_code, msg, "Gate 4", resultados)}

    return {
        "aprovado": True,
        "bloqueado_em": None,
        "motivo": "Passou em todos os filtros",
        "reason_code": REJECT_CODE_PASSED,
        "detalhes": resultados,
    }

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