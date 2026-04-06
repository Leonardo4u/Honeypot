"""
Script de liquidação manual dos sinais pendentes CLV.
Resultados buscados na web em 05/04/2026.

SINAIS PULADOS (verificar manualmente):
  #80 Nantes vs Strasbourg - placar final não confirmado
  #82 Flamengo vs Palmeiras - em 02/04 Flamengo jogou FORA (Bragantino 3x0 Fla). Verifique.
  #83 Le Havre vs Auxerre   - jogo de hoje, aguarde resultado

Como rodar:
    python liquidar_pendentes.py
    python liquidar_pendentes.py --id 68   (liquidar só um)
"""

import sqlite3
import argparse
from datetime import datetime

DB_PATH = "data/edge_protocol.db"

RESULTADOS = {
    68: {
        "jogo": "Grêmio vs Vitoria",
        "placar": "2-0",
        "mercado": "over_2.5",
        "odd": 2.28,
        "stake": 1.0,
        "resultado": "vermelho",  # 2 gols = under 2.5
        "notas": "Grêmio 2x0 Vitoria. Total 2 gols. Under 2.5 → vermelho."
    },
    71: {
        "jogo": "Villarreal vs Real Sociedad",
        "placar": "3-1",
        "mercado": "over_2.5",
        "odd": 2.00,
        "stake": 1.0,
        "resultado": "verde",  # 4 gols
        "notas": "Villarreal 3x1 Real Sociedad. Total 4 gols. Over 2.5 → verde."
    },
    72: {
        "jogo": "Genoa vs Udinese",
        "placar": "0-2",
        "mercado": "over_2.5",
        "odd": 2.53,
        "stake": 1.0,
        "resultado": "vermelho",  # 2 gols = under 2.5
        "notas": "Genoa 0x2 Udinese. Total 2 gols. Under 2.5 → vermelho."
    },
    73: {
        "jogo": "Everton vs Chelsea",
        "placar": "3-0",
        "mercado": "1x2_casa",
        "odd": 3.50,
        "stake": 1.0,
        "resultado": "verde",
        "notas": "Everton 3x0 Chelsea. Casa venceu → verde."
    },
    74: {
        "jogo": "Everton vs Chelsea",
        "placar": "3-0",
        "mercado": "over_2.5",
        "odd": 1.95,
        "stake": 1.0,
        "resultado": "verde",  # 3 gols
        "notas": "Everton 3x0 Chelsea. Total 3 gols. Over 2.5 → verde."
    },
    75: {
        "jogo": "Sevilla vs Valencia",
        "placar": "0-2",
        "mercado": "1x2_casa",
        "odd": 2.38,
        "stake": 1.0,
        "resultado": "vermelho",
        "notas": "Sevilla 0x2 Valencia. Fora venceu → vermelho."
    },
    76: {
        "jogo": "Sevilla vs Valencia",
        "placar": "0-2",
        "mercado": "over_2.5",
        "odd": 2.50,
        "stake": 1.0,
        "resultado": "vermelho",  # 2 gols = under 2.5
        "notas": "Sevilla 0x2 Valencia. Total 2 gols. Under 2.5 → vermelho."
    },
    77: {
        "jogo": "Nice vs Paris Saint Germain",
        "placar": "0-4",
        "mercado": "over_2.5",
        "odd": 2.20,
        "stake": 1.0,
        "resultado": "verde",  # 4 gols
        "notas": "Nice 0x4 PSG. Total 4 gols. Over 2.5 → verde."
    },
    79: {
        "jogo": "Bologna vs Lazio",
        "placar": "0-2",
        "mercado": "over_2.5",
        "odd": 2.25,
        "stake": 1.0,
        "resultado": "vermelho",  # 2 gols = under 2.5
        "notas": "Bologna 0x2 Lazio. Total 2 gols. Under 2.5 → vermelho."
    },
    80: {
        "jogo": "Nantes vs Strasbourg",
        "placar": "VERIFICAR",
        "mercado": "over_2.5",
        "odd": 1.96,
        "stake": 1.0,
        "resultado": None,
        "notas": "Placar final não confirmado. Defina resultado e rode: python liquidar_pendentes.py --id 80"
    },
    82: {
        "jogo": "Flamengo vs Palmeiras",
        "placar": "VERIFICAR",
        "mercado": "1x2_casa",
        "odd": 1.90,
        "stake": 1.0,
        "resultado": None,
        "notas": "Em 02/04 Flamengo jogou FORA (Bragantino 3x0 Fla). Verifique data/mandante no banco."
    },
    83: {
        "jogo": "Le Havre vs Auxerre",
        "placar": "HOJE",
        "mercado": "over_2.5",
        "odd": 2.38,
        "stake": 1.0,
        "resultado": None,
        "notas": "Jogo de hoje (05/04). Aguarde resultado e rode: python liquidar_pendentes.py --id 83"
    },
}


def calcular_lucro(odd, resultado, stake):
    if resultado == "verde":
        return round((odd - 1) * stake, 4)
    elif resultado == "vermelho":
        return round(-stake, 4)
    return 0.0


def liquidar_sinal(conn, sinal_id, resultado, lucro_unidades):
    c = conn.cursor()
    c.execute(
        "UPDATE sinais SET status = ?, resultado = ?, lucro_unidades = ? WHERE id = ?",
        (resultado, resultado, lucro_unidades, sinal_id)
    )
    c.execute(
        """UPDATE clv_tracking SET status = 'liquidado_manual'
           WHERE sinal_id = ? AND status = 'aguardando'""",
        (sinal_id,)
    )
    conn.commit()


def main(filtro_id=None):
    conn = sqlite3.connect(DB_PATH)
    print(f"\n=== LIQUIDAÇÃO MANUAL — {datetime.now().strftime('%d/%m/%Y %H:%M')} ===\n")

    liquidados = []
    skipped = []

    for sinal_id, dados in RESULTADOS.items():
        if filtro_id and sinal_id != filtro_id:
            continue

        if dados["resultado"] is None:
            print(f"⚠️  #{sinal_id} [{dados['mercado']}] {dados['jogo']} → PULADO")
            print(f"   {dados['notas']}\n")
            skipped.append(sinal_id)
            continue

        lucro = calcular_lucro(dados["odd"], dados["resultado"], dados["stake"])
        liquidar_sinal(conn, sinal_id, dados["resultado"], lucro)

        emoji = "✅" if dados["resultado"] == "verde" else "❌"
        print(f"{emoji} #{sinal_id} [{dados['mercado']}] {dados['jogo']}")
        print(f"   Placar: {dados['placar']} | Odd: {dados['odd']} | {dados['resultado'].upper()} | Lucro: {lucro:+.4f} un\n")
        liquidados.append(sinal_id)

    conn.close()

    print("=" * 50)
    print(f"Liquidados : {len(liquidados)} → {liquidados}")
    print(f"Pendentes  : {len(skipped)}  → {skipped}")

    verdes    = [i for i in liquidados if RESULTADOS[i]["resultado"] == "verde"]
    vermelhos = [i for i in liquidados if RESULTADOS[i]["resultado"] == "vermelho"]
    lucro_total = sum(
        calcular_lucro(RESULTADOS[i]["odd"], RESULTADOS[i]["resultado"], RESULTADOS[i]["stake"])
        for i in liquidados
    )
    print(f"Verdes     : {len(verdes)} | Vermelhos: {len(vermelhos)}")
    print(f"Lucro total: {lucro_total:+.4f} unidades")

    if skipped:
        print(f"\n⚠️  Ainda precisam de verificação manual: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Liquidar apenas um sinal (ex: --id 80)")
    args = parser.parse_args()
    main(filtro_id=args.id)