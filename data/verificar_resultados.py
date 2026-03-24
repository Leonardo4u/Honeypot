import requests
import os
import sys
from datetime import datetime, date
from dotenv import load_dotenv
from ingestion_resilience import request_with_retry

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

LIGAS_IDS = {
    "EPL": 39,
    "Premier League": 39,
    "Brasileirao Serie A": 71,
    "Brasileirao": 71,
    "Brazil": 71,
}

HEADERS = {
    "x-rapidapi-host": "v3.football.api-sports.io",
    "x-rapidapi-key": API_FOOTBALL_KEY
}

def buscar_resultado_jogo(time_casa, time_fora, data=None):
    """
    Busca o resultado real de um jogo na API-Football.
    Retorna o placar final ou None se não encontrado.
    """
    if not data:
        data = str(date.today())

    try:
        result = request_with_retry(
            url="https://v3.football.api-sports.io/fixtures",
            headers=HEADERS,
            params={
                "date": data,
                "timezone": "America/Sao_Paulo"
            },
            timeout=10,
            attempts=3,
            backoff_seconds=0.8,
            source_name="api_football:fixtures",
        )

        if not result["ok"]:
            print(
                "Erro API resultados "
                f"[{result.get('status')}] "
                f"status_code={result.get('status_code')} "
                f"attempts={result.get('attempts_used')}"
            )
            return None

        fixtures = result["data"].get("response", [])

        for fixture in fixtures:
            home = fixture["teams"]["home"]["name"]
            away = fixture["teams"]["away"]["name"]

            home_match = time_casa.lower() in home.lower() or home.lower() in time_casa.lower()
            away_match = time_fora.lower() in away.lower() or away.lower() in time_fora.lower()

            if home_match and away_match:
                status = fixture["fixture"]["status"]["short"]

                if status in ["FT", "AET", "PEN"]:
                    gols_casa = fixture["goals"]["home"]
                    gols_fora = fixture["goals"]["away"]
                    return {
                        "status": "finalizado",
                        "gols_casa": gols_casa,
                        "gols_fora": gols_fora,
                        "placar": f"{gols_casa}-{gols_fora}"
                    }
                elif status in ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]:
                    return {"status": "em_andamento"}
                else:
                    return {"status": "nao_iniciado"}

        return None

    except Exception as e:
        print(f"Erro ao buscar resultado: {e}")
        return None

def avaliar_mercado(resultado, mercado, odd):
    """
    Avalia se a aposta ganhou ou perdeu baseado no resultado e mercado.
    """
    if not resultado or resultado["status"] != "finalizado":
        return None

    gols_casa = resultado["gols_casa"]
    gols_fora = resultado["gols_fora"]
    total_gols = gols_casa + gols_fora

    if mercado == "1x2_casa":
        ganhou = gols_casa > gols_fora
    elif mercado == "1x2_fora":
        ganhou = gols_fora > gols_casa
    elif mercado == "over_2.5":
        ganhou = total_gols > 2.5
    elif mercado == "under_2.5":
        ganhou = total_gols < 2.5
    elif mercado == "btts_sim":
        ganhou = gols_casa > 0 and gols_fora > 0
    else:
        return None

    if ganhou:
        return {
            "resultado": "verde",
            "lucro": round(odd - 1, 4)
        }
    else:
        return {
            "resultado": "vermelho",
            "lucro": -1.0
        }

if __name__ == "__main__":
    print("=== TESTE DE VERIFICAÇÃO DE RESULTADO ===\n")
    resultado = buscar_resultado_jogo("Arsenal", "Bournemouth")
    if resultado:
        print(f"Status: {resultado['status']}")
        if resultado['status'] == 'finalizado':
            print(f"Placar: {resultado['placar']}")
    else:
        print("Jogo não encontrado.")