import requests
import os
import sys
from datetime import datetime, date, timezone
from dotenv import load_dotenv
from ingestion_resilience import request_with_retry
import unicodedata

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

STATUS_FINALIZADO = {"FT", "AET", "PEN"}
STATUS_ANDAMENTO = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}


def _normalizar_nome_time(nome):
    txt = unicodedata.normalize("NFKD", str(nome or ""))
    txt = txt.encode("ascii", "ignore").decode("ascii")
    txt = " ".join(txt.lower().replace("-", " ").split())
    return txt


def _match_times(time_casa, time_fora, home_api, away_api):
    casa_ref = _normalizar_nome_time(time_casa)
    fora_ref = _normalizar_nome_time(time_fora)
    casa_api = _normalizar_nome_time(home_api)
    fora_api = _normalizar_nome_time(away_api)

    score = 0
    if casa_ref == casa_api:
        score += 10
    elif casa_ref in casa_api or casa_api in casa_ref:
        score += 6

    if fora_ref == fora_api:
        score += 10
    elif fora_ref in fora_api or fora_api in fora_ref:
        score += 6

    return score


def _extrair_kickoff_utc(fixture):
    kickoff = fixture.get("fixture", {}).get("date")
    if not kickoff:
        return None
    try:
        if kickoff.endswith("Z"):
            kickoff = kickoff.replace("Z", "+00:00")
        return datetime.fromisoformat(kickoff)
    except Exception:
        return None


def _avaliar_fixture(fixture, time_casa, time_fora, horario_ref=None):
    home = fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("teams", {}).get("away", {}).get("name", "")
    name_score = _match_times(time_casa, time_fora, home, away)
    if name_score <= 0:
        return None

    diff_min = 10**9
    kickoff_dt = _extrair_kickoff_utc(fixture)
    if horario_ref and kickoff_dt:
        try:
            ref_dt = datetime.strptime(horario_ref, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            diff_min = abs((kickoff_dt - ref_dt).total_seconds() / 60.0)
        except Exception:
            diff_min = 10**9

    fixture_id = str(fixture.get("fixture", {}).get("id", ""))
    return {
        "fixture": fixture,
        "name_score": name_score,
        "diff_min": diff_min,
        "fixture_id": fixture_id,
    }


def _resolver_status_fixture(fixture):
    status = fixture.get("fixture", {}).get("status", {}).get("short")
    goals = fixture.get("goals", {})
    gols_casa = goals.get("home")
    gols_fora = goals.get("away")

    payload = {
        "fixture_id_api": str(fixture.get("fixture", {}).get("id", "")),
        "fixture_data_api": str(fixture.get("fixture", {}).get("date", ""))[:10],
    }

    if status in STATUS_FINALIZADO:
        payload.update(
            {
                "status": "finalizado",
                "gols_casa": gols_casa,
                "gols_fora": gols_fora,
                "placar": f"{gols_casa}-{gols_fora}",
            }
        )
        return payload

    if status in STATUS_ANDAMENTO:
        payload["status"] = "em_andamento"
        return payload

    payload["status"] = "nao_iniciado"
    return payload


def _buscar_fixture_por_id(fixture_id):
    if not fixture_id:
        return None

    result = request_with_retry(
        url="https://v3.football.api-sports.io/fixtures",
        headers=HEADERS,
        params={
            "id": fixture_id,
            "timezone": "America/Sao_Paulo",
        },
        timeout=10,
        attempts=3,
        backoff_seconds=0.8,
        source_name="api_football:fixtures_by_id",
    )
    if not result.get("ok"):
        return None

    fixtures = result.get("data", {}).get("response", [])
    if not fixtures:
        return None
    return fixtures[0]


def _buscar_fixture_por_janela(time_casa, time_fora, data_base, horario_ref=None, janela_dias=2):
    candidatos = []
    for offset in range(-janela_dias, janela_dias + 1):
        data_alvo = (data_base.fromordinal(data_base.toordinal() + offset)).isoformat()
        result = request_with_retry(
            url="https://v3.football.api-sports.io/fixtures",
            headers=HEADERS,
            params={
                "date": data_alvo,
                "timezone": "America/Sao_Paulo",
            },
            timeout=10,
            attempts=3,
            backoff_seconds=0.8,
            source_name=f"api_football:fixtures:{data_alvo}",
        )
        if not result.get("ok"):
            continue

        fixtures = result.get("data", {}).get("response", [])
        for fixture in fixtures:
            avaliado = _avaliar_fixture(fixture, time_casa, time_fora, horario_ref=horario_ref)
            if avaliado:
                candidatos.append(avaliado)

    if not candidatos:
        return None

    candidatos.sort(key=lambda c: (-c["name_score"], c["diff_min"], c["fixture_id"]))
    return candidatos[0]["fixture"]

def buscar_resultado_jogo(time_casa, time_fora, data=None, horario=None, fixture_id=None):
    """
    Busca o resultado real de um jogo na API-Football.
    Retorna o placar final ou None se não encontrado.
    """
    data_base = None
    if data:
        try:
            data_base = datetime.strptime(str(data), "%Y-%m-%d").date()
        except Exception:
            data_base = None

    if data_base is None and horario:
        try:
            data_base = datetime.strptime(horario, "%Y-%m-%dT%H:%M:%SZ").date()
        except Exception:
            data_base = None

    if data_base is None:
        data_base = date.today()

    try:
        fixture = _buscar_fixture_por_id(fixture_id)
        match_strategy = None
        if fixture:
            match_strategy = "fixture_id"
        else:
            fixture = _buscar_fixture_por_janela(
                time_casa=time_casa,
                time_fora=time_fora,
                data_base=data_base,
                horario_ref=horario,
                janela_dias=2,
            )
            if fixture:
                match_strategy = "date_window"

        if not fixture:
            return None

        payload = _resolver_status_fixture(fixture)
        payload["match_strategy"] = match_strategy
        return payload

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