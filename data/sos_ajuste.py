import json
import os
import sys
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))

XG_PATH = os.path.join(os.path.dirname(__file__), "xg_dados.json")
SOS_PATH = os.path.join(os.path.dirname(__file__), "sos_dados.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")

LIGAS_UNDERSTAT = {
    "soccer_epl": "EPL",
    "soccer_spain_la_liga": "La_liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie_A",
    "soccer_france_ligue_one": "Ligue_1",
}

def carregar_xg():
    if not os.path.exists(XG_PATH):
        return {}
    with open(XG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def calcular_media_liga(xg_dados, campo="xg_marcado_casa"):
    valores = [v[campo] for v in xg_dados.values() if campo in v and v[campo] > 0]
    return round(sum(valores) / len(valores), 3) if valores else 1.3

def classificar_times_liga(xg_dados):
    if not xg_dados:
        return {}

    xg_geral = {}
    for time, dados in xg_dados.items():
        xg_ataque = (dados.get("xg_marcado_casa", 0) + dados.get("xg_marcado_fora", 0)) / 2
        xg_defesa = (dados.get("xg_sofrido_casa", 0) + dados.get("xg_sofrido_fora", 0)) / 2
        xg_geral[time] = {"xg_ataque": xg_ataque, "xg_defesa": xg_defesa}

    times_ordenados = sorted(xg_geral.items(), key=lambda x: x[1]["xg_ataque"], reverse=True)
    n = len(times_ordenados)
    top_33 = n // 3
    bot_33 = n - top_33

    classificacao = {}
    for i, (time, dados) in enumerate(times_ordenados):
        if i < top_33:
            tier = "forte"
        elif i >= bot_33:
            tier = "fraco"
        else:
            tier = "medio"
        classificacao[time] = {"tier": tier, **dados}

    return classificacao

def calcular_sos(time_casa, time_fora, liga_key):
    xg_dados = carregar_xg()

    if not xg_dados:
        return None

    media_xg_concedido = calcular_media_liga(xg_dados, "xg_sofrido_casa")
    media_xg_gerado = calcular_media_liga(xg_dados, "xg_marcado_fora")

    dados_casa = xg_dados.get(time_casa, {})
    dados_fora = xg_dados.get(time_fora, {})

    if not dados_casa or not dados_fora:
        return None

    xg_concedido_fora = dados_fora.get("xg_sofrido_fora", media_xg_concedido)
    xg_gerado_fora = dados_fora.get("xg_marcado_fora", media_xg_gerado)
    xg_concedido_casa = dados_casa.get("xg_sofrido_casa", media_xg_concedido)
    xg_gerado_casa = dados_casa.get("xg_marcado_casa", media_xg_gerado)

    return {
        "time_casa": time_casa,
        "time_fora": time_fora,
        "media_liga_xg_concedido": media_xg_concedido,
        "media_liga_xg_gerado": media_xg_gerado,
        "xg_concedido_defesa_fora": xg_concedido_fora,
        "xg_gerado_ataque_fora": xg_gerado_fora,
        "xg_concedido_defesa_casa": xg_concedido_casa,
        "xg_gerado_ataque_casa": xg_gerado_casa,
    }

def _faixa_cap_sos(source_quality):
    if source_quality in ("medias", "médias", "fallback", "fallback_sos"):
        return 0.85, 1.15
    return 0.7, 1.5


def ajustar_xg_por_sos(xg_bruto_casa, xg_bruto_fora, time_casa, time_fora, liga_key, source_quality="xG"):
    sos = calcular_sos(time_casa, time_fora, liga_key)

    if not sos:
        return xg_bruto_casa, xg_bruto_fora, "sem_sos", None

    media_concedido = sos["media_liga_xg_concedido"]
    media_gerado = sos["media_liga_xg_gerado"]

    fator_ataque_casa = (sos["xg_concedido_defesa_fora"] / media_concedido) if media_concedido > 0 else 1.0
    fator_defesa_casa = (sos["xg_gerado_ataque_fora"] / media_gerado) if media_gerado > 0 else 1.0
    fator_ataque_fora = (sos["xg_concedido_defesa_casa"] / media_concedido) if media_concedido > 0 else 1.0
    fator_defesa_fora = (sos["xg_gerado_ataque_casa"] / media_gerado) if media_gerado > 0 else 1.0

    fator_casa = round((fator_ataque_casa + fator_defesa_casa) / 2, 3)
    fator_fora = round((fator_ataque_fora + fator_defesa_fora) / 2, 3)

    cap_min, cap_max = _faixa_cap_sos(source_quality)
    fator_casa = max(cap_min, min(cap_max, fator_casa))
    fator_fora = max(cap_min, min(cap_max, fator_fora))

    xg_ajustado_casa = round(xg_bruto_casa * fator_casa, 3)
    xg_ajustado_fora = round(xg_bruto_fora * fator_fora, 3)

    detalhes = {
        "xg_bruto_casa": xg_bruto_casa,
        "xg_bruto_fora": xg_bruto_fora,
        "xg_ajustado_casa": xg_ajustado_casa,
        "xg_ajustado_fora": xg_ajustado_fora,
        "fator_casa": fator_casa,
        "fator_fora": fator_fora,
        "cap_min": cap_min,
        "cap_max": cap_max,
        "source_quality": source_quality,
        "sos": sos
    }

    return xg_ajustado_casa, xg_ajustado_fora, "sos_aplicado", detalhes

def comparar_probabilidades(xg_casa_bruto, xg_fora_bruto, xg_casa_ajustado, xg_fora_ajustado):
    try:
        from poisson import calcular_probabilidades

        prob_bruto = calcular_probabilidades(xg_casa_bruto, xg_fora_bruto)
        prob_ajustado = calcular_probabilidades(xg_casa_ajustado, xg_fora_ajustado)

        diff_casa = round(abs(prob_ajustado["prob_casa"] - prob_bruto["prob_casa"]) * 100, 2)
        diff_fora = round(abs(prob_ajustado["prob_fora"] - prob_bruto["prob_fora"]) * 100, 2)
        diff_max = max(diff_casa, diff_fora)

        resultado = {
            "prob_bruta_casa": round(prob_bruto["prob_casa"] * 100, 1),
            "prob_ajustada_casa": round(prob_ajustado["prob_casa"] * 100, 1),
            "prob_bruta_fora": round(prob_bruto["prob_fora"] * 100, 1),
            "prob_ajustada_fora": round(prob_ajustado["prob_fora"] * 100, 1),
            "diff_max_pct": diff_max,
            "ajuste_relevante": diff_max >= 8
        }

        if diff_max >= 8:
            print(f"⚠️  Ajuste SOS relevante: {diff_max:.1f}% de diferença")
            print(f"   Prob casa: {resultado['prob_bruta_casa']}% → {resultado['prob_ajustada_casa']}%")
            print(f"   Prob fora: {resultado['prob_bruta_fora']}% → {resultado['prob_ajustada_fora']}%")

        return resultado

    except Exception as e:
        print(f"Erro ao comparar probabilidades: {e}")
        return None

def calcular_xg_com_sos(time_casa, time_fora, liga_key="soccer_epl"):
    from xg_understat import calcular_media_gols_com_xg

    media_casa, media_fora, fonte = calcular_media_gols_com_xg(time_casa, time_fora)

    xg_ajustado_casa, xg_ajustado_fora, status, detalhes = ajustar_xg_por_sos(
        media_casa, media_fora, time_casa, time_fora, liga_key, source_quality=fonte
    )

    if detalhes:
        comparar_probabilidades(media_casa, media_fora, xg_ajustado_casa, xg_ajustado_fora)

    fonte_final = f"{fonte}+SOS" if status == "sos_aplicado" else f"{fonte}+fallback_sos"

    return xg_ajustado_casa, xg_ajustado_fora, fonte_final

if __name__ == "__main__":
    print("=== TESTE SOS ===\n")

    xg = carregar_xg()
    if not xg:
        print("Arquivo xg_dados.json não encontrado.")
        print("Rode python data/xg_understat.py primeiro.")
    else:
        print(f"Times com xG: {len(xg)}\n")

        classificacao = classificar_times_liga(xg)
        fortes = [t for t, d in classificacao.items() if d["tier"] == "forte"]
        fracos = [t for t, d in classificacao.items() if d["tier"] == "fraco"]

        print(f"Times fortes (top 33%): {fortes[:5]}")
        print(f"Times fracos (bot 33%): {fracos[:5]}")

        times_disponiveis = list(xg.keys())
        if len(times_disponiveis) >= 2:
            casa = times_disponiveis[0]
            fora = times_disponiveis[1]

            print(f"\nTeste SOS: {casa} vs {fora}")
            xg_casa, xg_fora, fonte = calcular_xg_com_sos(casa, fora, "soccer_epl")
            print(f"xG ajustado casa: {xg_casa}")
            print(f"xG ajustado fora: {xg_fora}")
            print(f"Fonte: {fonte}")