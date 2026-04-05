import requests
import json
import os
import argparse
import csv
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from model.team_name_normalizer import normalize

load_dotenv()

BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.dirname(__file__))
STATS_PATH = os.path.join(BOT_DATA_DIR, "medias_gols.json")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

MAPEAMENTO_NOMES = {
    "Bragantino-SP": "RB Bragantino",
    "Atletico Mineiro": "Atletico-MG",
    "Vasco da Gama": "Vasco DA Gama",
    "Grmio": "Gremio",
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


def _api_headers():
    return {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": API_FOOTBALL_KEY,
    }


def _historico_out_path(league_id):
    if int(league_id) == 71:
        return os.path.join(BOT_DATA_DIR, "historico_BRA1.csv")
    return os.path.join(BOT_DATA_DIR, f"historico_API_{int(league_id)}.csv")


def _season_years(seasons_back=3):
    now = datetime.now(timezone.utc)
    current = int(now.year)
    return [current - i for i in range(max(0, int(seasons_back)) + 1)]


def _get_fixtures_with_retry(params, attempts=3, backoff_seconds=0.8):
    """Consulta fixtures com retry/backoff leve para falhas transitrias."""
    last_exc = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        try:
            response = requests.get(
                "https://v3.football.api-sports.io/fixtures",
                headers=_api_headers(),
                params=params,
                timeout=20,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            return None, str(exc)

        if response.status_code == 200:
            try:
                return response.json(), None
            except Exception as exc:
                return None, f"json_error={exc}"

        if response.status_code in (429,) or 500 <= response.status_code <= 599:
            if attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue

        return None, f"status={response.status_code}"

    return None, str(last_exc) if last_exc else "unknown_error"


def _extract_fixture_rows(payload, league_label, season):
    """Extrai linhas normalizadas de uma resposta de fixtures da API-Football."""
    rows = []
    fixtures = payload.get("response", []) if isinstance(payload, dict) else []
    for item in fixtures:
        teams = item.get("teams", {}) if isinstance(item, dict) else {}
        goals = item.get("goals", {}) if isinstance(item, dict) else {}
        fixture = item.get("fixture", {}) if isinstance(item, dict) else {}

        home = normalize((teams.get("home") or {}).get("name"))
        away = normalize((teams.get("away") or {}).get("name"))
        gh = goals.get("home")
        ga = goals.get("away")
        dt = fixture.get("date", "")

        # Ignora partidas sem placar final confirmado.
        if not home or not away or gh is None or ga is None:
            continue

        rows.append(
            {
                "liga": league_label,
                "temporada": str(season),
                "time_casa": str(home),
                "time_fora": str(away),
                "gols_casa": int(gh),
                "gols_fora": int(ga),
                "data_jogo": str(dt)[:10],
            }
        )
    return rows


def fetch_historico_brasileirao(seasons=3, league_id=71):
    """
    Busca historico finalizado via API-Football /fixtures.

    Salva CSV no schema: liga, temporada, time_casa, time_fora, gols_casa, gols_fora, data_jogo.
    Exige minimo de 50 partidas para persistir.
    """
    if not API_FOOTBALL_KEY:
        print("API_FOOTBALL_KEY nao configurada.")
        return []

    league_id = int(league_id)
    league_label = "Brasileirao Serie A" if league_id == 71 else f"Brasileirao {league_id}"
    rows = []

    for season in _season_years(seasons_back=seasons):
        season_rows = []

        # Primeiro tenta a chamada simples (sem page), que no probe retorna 380 por temporada.
        payload, err = _get_fixtures_with_retry(
            {
                "league": league_id,
                "season": season,
                "status": "FT",
            }
        )
        if payload is None:
            print(f"[WARN] fixtures API falhou league={league_id} season={season}: {err}")
            continue

        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            print(f"[WARN] fixtures API retornou errors league={league_id} season={season}: {errors}")

        season_rows.extend(_extract_fixture_rows(payload, league_label, season))

        # Fallback paginado quando a resposta simples vier vazia.
        if not season_rows:
            page = 1
            total_pages = 1
            while page <= total_pages:
                pag_payload, pag_err = _get_fixtures_with_retry(
                    {
                        "league": league_id,
                        "season": season,
                        "status": "FT",
                        "page": page,
                    }
                )
                if pag_payload is None:
                    print(
                        f"[WARN] fixtures paginado falhou league={league_id} season={season} page={page}: {pag_err}"
                    )
                    break

                pag = pag_payload.get("paging", {}) if isinstance(pag_payload, dict) else {}
                total_pages = int(pag.get("total", 1) or 1)
                season_rows.extend(_extract_fixture_rows(pag_payload, league_label, season))
                page += 1

        rows.extend(season_rows)
        print(f"season={season} fixtures={len(season_rows)}")

    if len(rows) < 50:
        print(f"[WARN] historico insuficiente para league_id={league_id}: matches={len(rows)} (<50)")
        return rows
    unique_rows = []
    seen = set()
    for row in rows:
        key = (row["time_casa"], row["time_fora"], row["data_jogo"])
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    os.makedirs(BOT_DATA_DIR, exist_ok=True)
    out_path = _historico_out_path(league_id)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["liga", "temporada", "time_casa", "time_fora", "gols_casa", "gols_fora", "data_jogo"],
        )
        writer.writeheader()
        writer.writerows(unique_rows)
    print(f"Historico salvo: {out_path} | matches={len(unique_rows)}")
    return unique_rows


def fetch_historico_br_ligas(seasons=3):
    """Executa fetch historico para Serie A (71)."""
    bra1 = fetch_historico_brasileirao(seasons=seasons, league_id=71)
    return {"BRA1": bra1}

def buscar_stats_api_football(liga_key, temporada=2024):
    if not API_FOOTBALL_KEY:
        print("API_FOOTBALL_KEY no configurada.")
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
            nome = normalize(time["team"]["name"])
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
    print("=== ATUALIZANDO MDIAS DE GOLS ===\n")
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
        print("Criando arquivo de mdias pela primeira vez...")
        return salvar_medias_manuais()

    with open(STATS_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Atualizacao de stats e historico API-Football")
    parser.add_argument("--fetch-historico-br", action="store_true", help="Busca historico BR Serie A via API-Football")
    parser.add_argument("--seasons", type=int, default=3, help="Qtde de temporadas passadas alem da atual")
    args = parser.parse_args()

    if args.fetch_historico_br:
        fetch_historico_br_ligas(seasons=args.seasons)
    elif API_FOOTBALL_KEY:
        atualizar_todas_ligas()
    else:
        print("API_FOOTBALL_KEY nao configurada.")
        salvar_medias_manuais()