import requests
import os
from dotenv import load_dotenv
from ingestion_resilience import request_with_retry

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
SHARP_BOOKMAKERS = {"pinnacle", "betfair", "betfair_ex_eu"}

PROVIDER_STATUS_TO_HEALTH = {
    "ok": "ok",
    "simulated": "ok",
    "timeout": "timeout",
    "http_error": "http_error",
    "connection_error": "connection_error",
    "empty_payload": "empty_payload",
}


def normalizar_provider_status(status):
    return PROVIDER_STATUS_TO_HEALTH.get(status, "unknown_error")


def atualizar_contadores_provider_health(provider_health, status):
    categoria = normalizar_provider_status(status)
    if categoria not in provider_health:
        provider_health[categoria] = 0
    provider_health[categoria] += 1
    return categoria


def buscar_jogos_com_odds_com_status(liga, mercados="h2h,totals"):
    if not API_KEY:
        print("ODDS_API_KEY não configurada. Usando dados simulados.")
        return {
            "ok": True,
            "status": "simulated",
            "data": _dados_simulados(),
            "status_code": None,
            "attempts_used": 0,
            "error": None,
        }

    url = f"{BASE_URL}/sports/{liga}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": mercados,
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }

    result = request_with_retry(
        url=url,
        params=params,
        timeout=10,
        attempts=3,
        backoff_seconds=0.8,
        source_name=f"odds_api:{liga}",
    )

    if result.get("ok"):
        return {
            "ok": True,
            "status": result.get("status", "ok"),
            "data": result.get("data", []),
            "status_code": result.get("status_code"),
            "attempts_used": result.get("attempts_used"),
            "error": None,
        }

    print(
        "Erro API odds "
        f"[{result.get('status')}] "
        f"status_code={result.get('status_code')} "
        f"attempts={result.get('attempts_used')} "
        f"error={result.get('error')}"
    )
    return {
        "ok": False,
        "status": result.get("status", "unknown_error"),
        "data": [],
        "status_code": result.get("status_code"),
        "attempts_used": result.get("attempts_used"),
        "error": result.get("error"),
    }

def buscar_jogos_com_odds(liga, mercados="h2h,totals"):
    result = buscar_jogos_com_odds_com_status(liga, mercados=mercados)
    return result.get("data", [])

def extrair_melhor_odd(jogo):
    melhor_casa = 0
    melhor_fora = 0
    melhor_over = 0
    melhor_under = 0
    melhor_casa_sharp = False
    melhor_fora_sharp = False
    melhor_over_sharp = False
    melhor_under_sharp = False

    for bookmaker in jogo.get("bookmakers", []):
        bookmaker_key = bookmaker.get("key", "")
        is_sharp = bookmaker_key in SHARP_BOOKMAKERS
        for market in bookmaker.get("markets", []):
            if market["key"] == "h2h":
                for o in market["outcomes"]:
                    if o["name"] == jogo["home_team"]:
                        if o["price"] > melhor_casa:
                            melhor_casa = o["price"]
                            melhor_casa_sharp = is_sharp
                    elif o["name"] == jogo["away_team"]:
                        if o["price"] > melhor_fora:
                            melhor_fora = o["price"]
                            melhor_fora_sharp = is_sharp

            elif market["key"] == "totals":
                for o in market["outcomes"]:
                    if o["name"] == "Over":
                        if o["price"] > melhor_over:
                            melhor_over = o["price"]
                            melhor_over_sharp = is_sharp
                    elif o["name"] == "Under":
                        if o["price"] > melhor_under:
                            melhor_under = o["price"]
                            melhor_under_sharp = is_sharp

    source_quality = {
        "1x2_casa": "sharp" if melhor_casa_sharp and melhor_fora_sharp else "fallback",
        "1x2_fora": "sharp" if melhor_fora_sharp and melhor_casa_sharp else "fallback",
        "over_2.5": "sharp" if melhor_over_sharp and melhor_under_sharp else "fallback",
        "under_2.5": "sharp" if melhor_under_sharp and melhor_over_sharp else "fallback",
    }

    return {
        "casa": round(melhor_casa, 2),
        "fora": round(melhor_fora, 2),
        "over_2.5": round(melhor_over, 2),
        "under_2.5": round(melhor_under, 2),
        "source_quality": source_quality,
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
            "odds": {
                "casa": odds["casa"],
                "fora": odds["fora"],
                "over_2.5": odds["over_2.5"],
                "under_2.5": odds["under_2.5"],
            },
            "source_quality": odds.get("source_quality", {}),
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