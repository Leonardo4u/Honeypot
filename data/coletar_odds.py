import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"

def buscar_jogos_com_odds(liga, mercados="h2h,totals"):
    if not API_KEY:
        print("ODDS_API_KEY não configurada. Usando dados simulados.")
        return _dados_simulados()

    url = f"{BASE_URL}/sports/{liga}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": mercados,
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erro na API: {response.status_code} — {response.text}")
            return []
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return []

def extrair_melhor_odd(jogo):
    melhor_casa = 0
    melhor_fora = 0
    melhor_over = 0
    melhor_under = 0

    for bookmaker in jogo.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market["key"] == "h2h":
                for o in market["outcomes"]:
                    if o["name"] == jogo["home_team"]:
                        melhor_casa = max(melhor_casa, o["price"])
                    elif o["name"] == jogo["away_team"]:
                        melhor_fora = max(melhor_fora, o["price"])

            elif market["key"] == "totals":
                for o in market["outcomes"]:
                    if o["name"] == "Over":
                        melhor_over = max(melhor_over, o["price"])
                    elif o["name"] == "Under":
                        melhor_under = max(melhor_under, o["price"])

    return {
        "casa": round(melhor_casa, 2),
        "fora": round(melhor_fora, 2),
        "over_2.5": round(melhor_over, 2),
        "under_2.5": round(melhor_under, 2)
    }

def formatar_jogos(dados_api):
    from datetime import datetime, timezone, timedelta

    agora = datetime.now(timezone.utc)
    limite = agora + timedelta(hours=12)

    jogos = []
    for jogo in dados_api:
        horario_str = jogo.get("commence_time", "")
        try:
            horario = datetime.strptime(horario_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if horario < agora or horario > limite:
                continue
        except Exception:
            continue

        odds = extrair_melhor_odd(jogo)
        jogos.append({
            "id": jogo.get("id"),
            "liga": jogo.get("sport_title"),
            "jogo": f"{jogo['home_team']} vs {jogo['away_team']}",
            "home_team": jogo["home_team"],
            "away_team": jogo["away_team"],
            "horario": horario_str,
            "odds": odds
        })

    return jogos

def _dados_simulados():
    return [
        {
            "id": "sim_001",
            "sport_title": "Premier League",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "commence_time": "2025-03-18T17:30:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Arsenal", "price": 1.92},
                                {"name": "Chelsea", "price": 4.10},
                                {"name": "Draw", "price": 3.50}
                            ]
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.85},
                                {"name": "Under", "price": 1.95}
                            ]
                        }
                    ]
                }
            ]
        }
    ]

if __name__ == "__main__":
    print("=== TESTE DE COLETA DE ODDS ===\n")
    dados = buscar_jogos_com_odds("soccer_epl")
    jogos = formatar_jogos(dados)
    for j in jogos:
        print(f"Jogo: {j['jogo']}")
        print(f"Odds: {j['odds']}")
        print()