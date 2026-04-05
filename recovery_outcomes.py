import csv
import json
import difflib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from data.ingestion_resilience import request_with_retry
from data.verificar_resultados import (
    HEADERS,
    LIGAS_IDS,
    STATUS_FINALIZADO,
    _match_times,
    _normalizar_nome_time,
)

PICKS_PATH = Path("data/picks_log.csv")
AUDIT_PATH = Path("data/recovery_audit.json")


@dataclass
class UniqueGame:
    date: str
    league: str
    team_home: str
    team_away: str
    prediction_ids: List[str]
    markets: Dict[str, List[str]]


def _load_orphans() -> List[dict]:
    with PICKS_PATH.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("outcome") not in ("0", "1")]


def _build_unique_games(orfaos: List[dict]) -> Dict[Tuple[str, str, str, str], UniqueGame]:
    grouped: Dict[Tuple[str, str, str, str], UniqueGame] = {}
    for r in orfaos:
        date = str(r.get("timestamp") or "")[:10]
        league = str(r.get("league") or "").strip()
        team_home = str(r.get("team_home") or "").strip()
        team_away = str(r.get("team_away") or "").strip()
        market = str(r.get("market") or "").strip()
        pred_id = str(r.get("prediction_id") or "").strip()

        key = (date, league, team_home, team_away)
        if key not in grouped:
            grouped[key] = UniqueGame(
                date=date,
                league=league,
                team_home=team_home,
                team_away=team_away,
                prediction_ids=[],
                markets=defaultdict(list),
            )
        grouped[key].prediction_ids.append(pred_id)
        grouped[key].markets[market].append(pred_id)

    return grouped


def _fetch_fixtures_by_date(date_str: str) -> List[dict]:
    result = request_with_retry(
        url="https://v3.football.api-sports.io/fixtures",
        headers=HEADERS,
        params={
            "date": date_str,
            "timezone": "America/Sao_Paulo",
        },
        timeout=10,
        attempts=3,
        backoff_seconds=0.8,
        source_name=f"recovery_outcomes:fixtures:{date_str}",
    )
    if not result.get("ok"):
        return []
    payload = result.get("data") or {}
    return payload.get("response") or []


def _derive_outcome(market: str, gols_casa: int, gols_fora: int) -> Optional[str]:
    total = gols_casa + gols_fora
    if market == "1x2_casa":
        return "1" if gols_casa > gols_fora else "0"
    if market == "1x2_fora":
        return "1" if gols_fora > gols_casa else "0"
    if market == "over_2.5":
        return "1" if total > 2 else "0"
    if market == "under_2.5":
        return "1" if total < 3 else "0"
    return None


def _league_match_confidence(league_csv: str, fixture: dict) -> Tuple[bool, bool]:
    csv_norm = _normalizar_nome_time(league_csv)
    fixture_league = str((fixture.get("league") or {}).get("name") or "")
    fixture_norm = _normalizar_nome_time(fixture_league)
    fixture_league_id = (fixture.get("league") or {}).get("id")

    expected_id = LIGAS_IDS.get(league_csv)
    if expected_id is not None and fixture_league_id == expected_id:
        return True, True

    if csv_norm and fixture_norm and csv_norm == fixture_norm:
        return True, True

    # League approximation fallback (e.g. Brazil Serie A vs Brasileirao Serie A).
    if csv_norm and fixture_norm:
        if csv_norm in fixture_norm or fixture_norm in csv_norm:
            return True, False
        ratio = difflib.SequenceMatcher(None, csv_norm, fixture_norm).ratio()
        if ratio >= 0.80:
            return True, False

    return False, False


def _select_best_fixture(game: UniqueGame, fixtures: List[dict]) -> Tuple[Optional[dict], str, float]:
    home_ref = game.team_home
    away_ref = game.team_away

    best_high: Tuple[Optional[dict], float] = (None, -1.0)
    best_medium: Tuple[Optional[dict], float] = (None, -1.0)
    best_low: Tuple[Optional[dict], float] = (None, -1.0)

    for fixture in fixtures:
        status = str(((fixture.get("fixture") or {}).get("status") or {}).get("short") or "")
        if status not in STATUS_FINALIZADO:
            continue

        teams = fixture.get("teams") or {}
        home_api = str((teams.get("home") or {}).get("name") or "")
        away_api = str((teams.get("away") or {}).get("name") or "")

        score = _match_times(home_ref, away_ref, home_api, away_api)
        if score <= 0:
            continue

        home_norm = _normalizar_nome_time(home_ref)
        away_norm = _normalizar_nome_time(away_ref)
        api_home_norm = _normalizar_nome_time(home_api)
        api_away_norm = _normalizar_nome_time(away_api)

        exact_teams = home_norm == api_home_norm and away_norm == api_away_norm
        league_match, league_exact = _league_match_confidence(game.league, fixture)

        # Similaridade no par de times para fallback BAIXO
        team_pair_ref = f"{home_norm}|{away_norm}"
        team_pair_api = f"{api_home_norm}|{api_away_norm}"
        sim = difflib.SequenceMatcher(None, team_pair_ref, team_pair_api).ratio()

        if exact_teams and league_exact:
            if score > best_high[1]:
                best_high = (fixture, float(score))
        elif exact_teams and league_match:
            if score > best_medium[1]:
                best_medium = (fixture, float(score))
        elif sim > 0.85:
            if sim > best_low[1]:
                best_low = (fixture, sim)

    if best_high[0] is not None:
        return best_high[0], "ALTO", best_high[1]
    if best_medium[0] is not None:
        return best_medium[0], "MEDIO", best_medium[1]
    if best_low[0] is not None:
        return best_low[0], "BAIXO", best_low[1]
    return None, "SEM_MATCH", 0.0


def _build_audit_entry(game: UniqueGame, fixture: Optional[dict], confianca: str, score: float) -> dict:
    key = f"{game.date}_{game.team_home}_{game.team_away}_{game.league}"

    if fixture is None:
        return key, {
            "gols_casa": None,
            "gols_fora": None,
            "status_api": None,
            "confianca": "SEM_MATCH",
            "match_score": score,
            "fixture_id": None,
            "outcomes_derivados": {},
            "prediction_ids_afetados": game.prediction_ids,
        }

    goals = fixture.get("goals") or {}
    gols_casa = goals.get("home")
    gols_fora = goals.get("away")
    status = str(((fixture.get("fixture") or {}).get("status") or {}).get("short") or "")
    fixture_id = str((fixture.get("fixture") or {}).get("id") or "")

    outcomes_derivados: Dict[str, str] = {}
    if gols_casa is not None and gols_fora is not None:
        for market in game.markets.keys():
            out = _derive_outcome(market, int(gols_casa), int(gols_fora))
            if out is not None:
                outcomes_derivados[market] = out

    return key, {
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
        "status_api": status,
        "confianca": confianca,
        "match_score": score,
        "fixture_id": fixture_id,
        "outcomes_derivados": outcomes_derivados,
        "prediction_ids_afetados": game.prediction_ids,
    }


def run() -> None:
    orfaos = _load_orphans()
    unique_games = _build_unique_games(orfaos)

    dates = sorted({g.date for g in unique_games.values() if g.date})
    fixtures_by_date = {d: _fetch_fixtures_by_date(d) for d in dates}

    audit = {}
    for game in unique_games.values():
        fixtures = fixtures_by_date.get(game.date, [])
        fixture, conf, score = _select_best_fixture(game, fixtures)
        key, entry = _build_audit_entry(game, fixture, conf, score)
        audit[key] = entry

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    print(f"Picks orfaos: {len(orfaos)}")
    print(f"Jogos unicos: {len(unique_games)}")
    print(f"Datas consultadas: {len(dates)} -> {dates}")
    print(f"Audit salvo em: {AUDIT_PATH.as_posix()}")


if __name__ == "__main__":
    run()
