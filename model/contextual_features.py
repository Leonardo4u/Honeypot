from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional


def _to_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value[: len(fmt)], fmt)
            except Exception:
                continue
    return None


def get_rest_days(team: str, match_date: Any, fixture_history: Optional[Iterable[Dict[str, Any]]] = None) -> int:
    target = _to_datetime(match_date)
    if target is None:
        return 0

    latest_prior = None
    for item in fixture_history or []:
        home = str(item.get("home_team") or "")
        away = str(item.get("away_team") or "")
        if team not in (home, away):
            continue
        dt = _to_datetime(item.get("date") or item.get("data_jogo") or item.get("horario"))
        if dt is None or dt >= target:
            continue
        if latest_prior is None or dt > latest_prior:
            latest_prior = dt

    if latest_prior is None:
        return 0
    return max(0, (target.date() - latest_prior.date()).days)


def get_congestion_score(team: str, match_date: Any, fixture_history: Optional[Iterable[Dict[str, Any]]] = None, window_days: int = 14) -> float:
    target = _to_datetime(match_date)
    if target is None:
        return 0.0

    start = target - timedelta(days=max(1, int(window_days)))
    count = 0
    for item in fixture_history or []:
        home = str(item.get("home_team") or "")
        away = str(item.get("away_team") or "")
        if team not in (home, away):
            continue
        dt = _to_datetime(item.get("date") or item.get("data_jogo") or item.get("horario"))
        if dt is None:
            continue
        if start <= dt < target:
            count += 1

    # 0-1 normalizado: 0 jogos -> 0.0, >=6 jogos/14d -> 1.0
    return max(0.0, min(1.0, float(count) / 6.0))


def get_h2h_features(home: str, away: str, n: int = 5, h2h_rows: Optional[Iterable[Dict[str, Any]]] = None):
    rows = []
    for item in h2h_rows or []:
        h = str(item.get("home_team") or item.get("time_casa") or "")
        a = str(item.get("away_team") or item.get("time_fora") or "")
        if {h, a} != {home, away}:
            continue
        rows.append(item)

    rows = rows[-max(1, int(n)) :]
    if not rows:
        return {
            "h2h_win_rate_home": 0.5,
            "h2h_avg_gols": 2.5,
            "h2h_shrinkage_weight": 0.0,
            "h2h_games": 0,
        }

    wins_home = 0
    total_gols = 0.0
    for item in rows:
        gc = float(item.get("gols_casa") or item.get("home_goals") or 0)
        gf = float(item.get("gols_fora") or item.get("away_goals") or 0)
        h = str(item.get("home_team") or item.get("time_casa") or "")
        a = str(item.get("away_team") or item.get("time_fora") or "")
        total_gols += gc + gf
        if h == home and gc > gf:
            wins_home += 1
        elif a == home and gf > gc:
            wins_home += 1

    games = len(rows)
    weight = max(0.0, min(1.0, games / max(1.0, float(n))))
    return {
        "h2h_win_rate_home": wins_home / games,
        "h2h_avg_gols": total_gols / games,
        "h2h_shrinkage_weight": weight,
        "h2h_games": games,
    }


def get_travel_bucket(home_city: Optional[str], away_city: Optional[str]) -> str:
    hc = str(home_city or "").strip().lower()
    ac = str(away_city or "").strip().lower()
    if not hc or not ac:
        return "nacional"
    if hc == ac:
        return "local"

    # Heurística leve para sem dependências externas: países diferentes por sufixo.
    if "," in hc and "," in ac:
        c1 = hc.split(",")[-1].strip()
        c2 = ac.split(",")[-1].strip()
        if c1 != c2:
            return "intercontinental"

    # fallback neutro
    return "regional"
