import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

STATS_PATH = os.path.join(os.path.dirname(__file__), "medias_gols.json")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

MAPEAMENTO_NOMES = {
    "Bragantino-SP": "RB Bragantino",
    "Atletico Mineiro": "Atletico-MG",
    "Vasco da Gama": "Vasco DA Gama",
    "Grêmio": "Gremio",
}

LIGAS_API_FOOTBALL = {
    "soccer_epl": 39,
    "soccer_spain_la_liga": 140,
    "soccer_germany_bundesliga": 78,
    "soccer_italy_serie_a": 135,
    "soccer_france_ligue_one": 61,
    "soccer_brazil_campeonato": 71,
    "soccer_uefa_champs_league": 2
}

def buscar_stats_api_football(liga_key, temporada=2024):
    if not API_FOOTBALL_KEY:
        print("API_FOOTBALL_KEY não configurada.")
        return {}

    liga_id = LIGAS_API_FOOTBALL.get(liga_key)
    if not liga_id:
        return {}

    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": API_FOOTBALL_KEY
    }

    medias = {}

    try:
        response = requests.get(
            "https://v3.football.api-sports.io/standings",
            headers=headers,
            params={"league": liga_id, "season": temporada},
            timeout=10
        )

        if response.status_code != 200:
            print(f"Erro API-Football: {response.status_code}")
            return {}

        dados = response.json()

        if not dados.get("response"):
            print(f"Sem dados para {liga_key}")
            return {}

        grupos = dados["response"][0]["league"]["standings"]
        standings = []
        for grupo in grupos:
            standings.extend(grupo)

        for time in standings:
            nome = time["team"]["name"]
            team_id = time["team"]["id"]
            jogos_casa = time["home"]["played"]
            jogos_fora = time["away"]["played"]
            gols_casa = time["home"]["goals"]["for"]
            gols_fora = time["away"]["goals"]["for"]
            gols_sofr_casa = time["home"]["goals"]["against"]
            gols_sofr_fora = time["away"]["goals"]["against"]

            media_casa = round(gols_casa / jogos_casa, 2) if jogos_casa > 0 else 1.2
            media_fora = round(gols_fora / jogos_fora, 2) if jogos_fora > 0 else 1.0
            media_sofr_casa = round(gols_sofr_casa / jogos_casa, 2) if jogos_casa > 0 else 1.2
            media_sofr_fora = round(gols_sofr_fora / jogos_fora, 2) if jogos_fora > 0 else 1.2

            dados_time = {
                "casa": media_casa,
                "fora": media_fora,
                "gols_sofridos_casa": media_sofr_casa,
                "gols_sofridos_fora": media_sofr_fora,
                "team_id": team_id
            }

            medias[nome] = dados_time

            for nome_api, nome_football in MAPEAMENTO_NOMES.items():
                if nome == nome_football:
                    medias[nome_api] = dados_time

        print(f"{len(medias)} times carregados.")
        return medias

    except Exception as e:
        print(f"Erro: {e}")
        return {}

def atualizar_todas_ligas():
    print("=== ATUALIZANDO MÉDIAS DE GOLS ===\n")
    todas_medias = {}

    for liga_key in LIGAS_API_FOOTBALL:
        print(f"Buscando {liga_key}...")
        medias = buscar_stats_api_football(liga_key)
        todas_medias.update(medias)

    if todas_medias:
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(todas_medias, f, ensure_ascii=False, indent=2)
        print(f"\nTotal: {len(todas_medias)} entradas salvas em medias_gols.json")
    else:
        print("Nenhuma stat encontrada.")

    return todas_medias

def salvar_medias_manuais():
    medias = {
        "Arsenal": {"casa": 2.1, "fora": 1.4, "gols_sofridos_casa": 0.8, "gols_sofridos_fora": 1.1},
        "Bournemouth": {"casa": 1.6, "fora": 1.1, "gols_sofridos_casa": 1.3, "gols_sofridos_fora": 1.5},
        "Brighton and Hove Albion": {"casa": 1.7, "fora": 1.3, "gols_sofridos_casa": 1.1, "gols_sofridos_fora": 1.3},
        "Brentford": {"casa": 1.8, "fora": 1.2, "gols_sofridos_casa": 1.2, "gols_sofridos_fora": 1.4},
        "Chelsea": {"casa": 1.9, "fora": 1.4, "gols_sofridos_casa": 1.0, "gols_sofridos_fora": 1.3},
        "Liverpool": {"casa": 2.4, "fora": 1.7, "gols_sofridos_casa": 0.7, "gols_sofridos_fora": 1.0},
        "Manchester City": {"casa": 2.2, "fora": 1.8, "gols_sofridos_casa": 0.8, "gols_sofridos_fora": 1.1},
        "Manchester United": {"casa": 1.5, "fora": 1.1, "gols_sofridos_casa": 1.3, "gols_sofridos_fora": 1.5},
        "Newcastle United": {"casa": 1.8, "fora": 1.2, "gols_sofridos_casa": 1.0, "gols_sofridos_fora": 1.3},
        "Tottenham Hotspur": {"casa": 1.7, "fora": 1.3, "gols_sofridos_casa": 1.2, "gols_sofridos_fora": 1.4},
        "Aston Villa": {"casa": 1.8, "fora": 1.3, "gols_sofridos_casa": 1.1, "gols_sofridos_fora": 1.3}
    }

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(medias, f, ensure_ascii=False, indent=2)
    print(f"Médias manuais salvas. Total: {len(medias)} times.")
    return medias

def carregar_medias():
    if not os.path.exists(STATS_PATH):
        print("Criando arquivo de médias pela primeira vez...")
        return salvar_medias_manuais()

    with open(STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    if API_FOOTBALL_KEY:
        atualizar_todas_ligas()
    else:
        print("API_FOOTBALL_KEY não configurada.")
        salvar_medias_manuais()