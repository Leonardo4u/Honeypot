import os
import sqlite3
from datetime import datetime

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

LIGA_ID_MAP = {
    "Premier League": 39,
    "EPL": 39,
    "La Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Brasileirao Serie A": 71,
    "Brazil Série A": 71,
    "UEFA Champions League": 2,
    "UEFA Europa League": 3,
}

_cache_standings = {}
_cache_ts = {}


def buscar_n_resultados():
    try:
        db = os.path.join(os.path.dirname(__file__), "..", "data", "edge_protocol.db")
        conn = sqlite3.connect(db)
        n = conn.execute("SELECT COUNT(*) FROM sinais WHERE status='finalizado'").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def calcular_teto_ev(n=0):
    if n < 50:
        return 0.20
    if n < 100:
        return 0.22
    if n < 200:
        return 0.25
    if n < 500:
        return 0.28
    return 0.30


def calcular_probabilidade_no_vig(odd_principal, odd_oponente):
    try:
        odd_a = float(odd_principal)
        odd_b = float(odd_oponente)
    except (TypeError, ValueError):
        return None

    if odd_a <= 0 or odd_b <= 0:
        return None

    prob_a = 1.0 / odd_a
    prob_b = 1.0 / odd_b
    soma = prob_a + prob_b
    if soma <= 0:
        return None

    return prob_a / soma


def gate1_ev_e_odd(ev, odd, mercado="", prob_modelo=None, odd_oponente_mercado=None):
    ev_minimo = {
        "1x2_casa": 0.06,
        "1x2_fora": 0.06,
        "over_2.5": 0.06,
        "under_2.5": 0.06,
        "over_1.5": 0.08,
        "btts_sim": 0.07,
        "dupla_chance_1x": 0.05,
        "dupla_chance_x2": 0.05,
        "dupla_chance_12": 0.05,
    }
    minimo = ev_minimo.get(mercado, get_market_ev_min(mercado))

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

    n = buscar_n_resultados()
    teto = calcular_teto_ev(n)
    if ev > teto:
        try:
            log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "bloqueados_ev.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] EV={ev*100:.1f}% odd={odd} mercado={mercado} n={n}\n")
        except Exception:
            pass
        return False, f"EV {ev*100:.1f}% acima do teto ({teto*100:.0f}%) — histórico: {n} apostas", REJECT_REASON_CODES["gate1_ev"]

    if prob_modelo and odd > 0:
        prob_mercado = 1 / odd
        prob_no_vig = calcular_probabilidade_no_vig(odd, odd_oponente_mercado)
        if prob_no_vig is not None:
            prob_mercado = prob_no_vig

        divergencia = prob_modelo - prob_mercado
        if divergencia > 0.20:
            return False, f"Divergência modelo-mercado: {divergencia*100:.1f}pp (máx 20pp)", REJECT_REASON_CODES["gate1_ev"]

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


def buscar_standings(liga_id, temporada=None):
    import requests

    if temporada is None:
        temporada = datetime.now().year
    key = f"{liga_id}_{temporada}"
    agora = datetime.now()

    if key in _cache_standings:
        if (agora - _cache_ts[key]).total_seconds() < 21600:
            return _cache_standings[key]

    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        return None

    try:
        r = requests.get(
            "https://v3.football.api-sports.io/standings",
            headers={
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "v3.football.api-sports.io",
            },
            params={"league": liga_id, "season": temporada},
            timeout=8,
        )
        if r.status_code != 200:
            return None

        dados = r.json().get("response", [])
        if not dados:
            return None

        standings = {}
        for grupo in dados[0]["league"]["standings"]:
            for t in grupo:
                standings[t["team"]["name"].lower()] = {
                    "posicao": t["rank"],
                    "pontos": t["points"],
                    "jogos_restantes": max(0, 38 - t["all"]["played"]),
                    "total_times": len(grupo),
                }

        _cache_standings[key] = standings
        _cache_ts[key] = agora
        return standings
    except Exception:
        return None


def gate5_motivacao(time_casa, time_fora, liga_nome):
    liga_id = LIGA_ID_MAP.get(liga_nome)
    if not liga_id:
        return True, "OK", 0
    if "Champions" in liga_nome or "Europa" in liga_nome:
        return True, "OK", 0

    standings = buscar_standings(liga_id)
    if not standings:
        return True, "OK", 0

    def achar_time(nome):
        nome_l = nome.lower()
        for k, v in standings.items():
            if nome_l in k or k in nome_l:
                return v
        return None

    dc = achar_time(time_casa)
    df = achar_time(time_fora)
    if not dc or not df:
        return True, "OK", 0

    def score_motivacao(d):
        p = d["pontos"]
        pos = d["posicao"]
        rest = d["jogos_restantes"]
        total = d["total_times"]
        zona = total - 3

        if pos > zona and rest <= 3 and (pos - zona) * 3 > rest * 3:
            return 20, "rebaixado"
        if pos == 1 and rest <= 3:
            return 20, "campeao"
        if rest <= 4:
            times_sorted = sorted(standings.items(), key=lambda x: -x[1]["pontos"])
            p4 = times_sorted[3][1]["pontos"] if len(times_sorted) > 3 else 0
            pzona = times_sorted[zona][1]["pontos"] if len(times_sorted) > zona else 0
            if (p4 - p) > rest * 3 and (p - pzona) > rest * 3:
                return 40, "sem_objetivo"
        return 80, "ok"

    sc, st = score_motivacao(dc)
    sf, stf = score_motivacao(df)

    if sc <= 20:
        return False, f"Gate 5: {time_casa} sem motivação ({st})", 0
    if sf <= 20:
        return False, f"Gate 5: {time_fora} sem motivação ({stf})", 0
    if sc <= 40 and sf <= 40:
        return False, "Gate 5: ambos sem objetivo matemático", 0

    pen = 0
    if sc <= 40:
        pen = -8
        print(f"[Gate5] {time_casa}: {st} -> -8pts")
    elif sf <= 40:
        pen = -8
        print(f"[Gate5] {time_fora}: {stf} -> -8pts")

    return True, "OK", pen

def aplicar_triple_gate(dados_sinal, sinais_hoje=0):
    resultados = {}

    ok, msg, reason_code = gate1_ev_e_odd(
        dados_sinal["ev"],
        dados_sinal["odd"],
        dados_sinal.get("mercado", ""),
        dados_sinal.get("prob_modelo", None),
        dados_sinal.get("odd_oponente_mercado", None),
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

    liga = dados_sinal.get("liga", "")
    tc = dados_sinal.get("time_casa", "")
    tf = dados_sinal.get("time_fora", "")
    penalizacao = 0

    if liga and tc and tf:
        ok, msg, pen = gate5_motivacao(tc, tf, liga)
        resultados["gate5"] = {"passou": ok, "msg": msg, "reason_code": "gate5_motivacao"}
        if not ok:
            return {"aprovado": False, **build_reject("gate5_motivacao", msg, "Gate 5", resultados)}
        penalizacao = pen
    else:
        resultados["gate5"] = {"passou": True, "msg": "pulado", "reason_code": None}

    return {
        "aprovado": True,
        "bloqueado_em": None,
        "motivo": "Passou em todos os filtros",
        "reason_code": REJECT_CODE_PASSED,
        "detalhes": resultados,
        "penalizacao_score": penalizacao,
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