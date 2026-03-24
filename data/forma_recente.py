import sqlite3
import json
import os
from dotenv import load_dotenv

load_dotenv()

FORMA_PATH = os.path.join(os.path.dirname(__file__), "forma_recente.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")

def calcular_forma_local(time, ultimos=5):
    """
    Calcula forma recente do time usando o banco de dados local.
    Usa os resultados já registrados no sistema.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT jogo, resultado, lucro_unidades
        FROM sinais
        WHERE (jogo LIKE ? OR jogo LIKE ?)
        AND status = 'finalizado'
        ORDER BY criado_em DESC
        LIMIT ?
    ''', (f'{time} vs %', f'% vs {time}', ultimos))
    jogos = c.fetchall()
    conn.close()

    if not jogos:
        return {
            "pontos": 0,
            "forma_percent": 50.0,
            "sequencia": [],
            "jogos": 0,
            "fonte": "local_fallback",
            "fallback": True,
            "source_marker": "fallback_no_local_history"
        }

    pontos = 0
    sequencia = []

    for jogo, resultado, lucro in jogos:
        times = jogo.split(' vs ')
        eh_casa = times[0].strip() == time

        if resultado == 'verde':
            if eh_casa:
                pontos += 3
                sequencia.append('V')
            else:
                pontos += 3
                sequencia.append('V')
        elif resultado == 'vermelho':
            sequencia.append('D')
        else:
            pontos += 1
            sequencia.append('E')

    n = len(jogos)
    forma_percent = round(pontos / (n * 3) * 100, 1) if n > 0 else 50

    return {
        "pontos": pontos,
        "forma_percent": forma_percent,
        "sequencia": sequencia,
        "jogos": n,
        "fonte": "local",
        "fallback": False,
        "source_marker": "local_history"
    }

def calcular_ajuste_forma(time_casa, time_fora):
    """
    Calcula ajuste contextual baseado na forma recente.
    Retorna fator entre -0.08 e +0.08
    """
    forma_casa_dados = calcular_forma_local(time_casa)
    forma_fora_dados = calcular_forma_local(time_fora)

    forma_casa = forma_casa_dados["forma_percent"] if forma_casa_dados else 50
    forma_fora = forma_fora_dados["forma_percent"] if forma_fora_dados else 50

    ajuste_casa = round((forma_casa - 50) / 50 * 0.08, 3)
    ajuste_fora = round((forma_fora - 50) / 50 * 0.08, 3)

    return ajuste_casa, ajuste_fora

def calcular_confianca_dados(time_casa, time_fora):
    """
    Calcula score de confiança baseado na quantidade de dados disponíveis.
    Quanto mais histórico, maior a confiança.
    """
    from atualizar_stats import carregar_medias
    medias = carregar_medias()

    tem_media_casa = time_casa in medias
    tem_media_fora = time_fora in medias

    jogos_casa = medias.get(time_casa, {}).get("jogos", 0)
    jogos_fora = medias.get(time_fora, {}).get("jogos", 0)

    confianca = 50

    if tem_media_casa and tem_media_fora:
        confianca += 20

    if jogos_casa >= 10:
        confianca += 10
    elif jogos_casa >= 5:
        confianca += 5

    if jogos_fora >= 10:
        confianca += 10
    elif jogos_fora >= 5:
        confianca += 5

    forma_casa = calcular_forma_local(time_casa)
    forma_fora = calcular_forma_local(time_fora)

    if forma_casa and not forma_casa.get("fallback", False):
        confianca += 5
    if forma_fora and not forma_fora.get("fallback", False):
        confianca += 5

    return min(100, confianca)

def carregar_forma():
    if not os.path.exists(FORMA_PATH):
        return {}
    with open(FORMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    print("=== TESTE DE FORMA LOCAL ===\n")
    print("O sistema calcula forma usando o banco de dados local.")
    print("Quanto mais resultados registrados, mais preciso fica.\n")

    from atualizar_stats import carregar_medias
    medias = carregar_medias()

    times_teste = ["Arsenal", "Liverpool", "Palmeiras", "Flamengo"]
    for time in times_teste:
        forma = calcular_forma_local(time)
        confianca = calcular_confianca_dados(time, "Liverpool")
        if forma:
            print(f"{time}: {forma['sequencia']} ({forma['forma_percent']}%)")
        else:
            print(f"{time}: sem histórico local ainda (usando padrão 50%)")
        print(f"  Confiança dos dados: {confianca}/100")
        print()