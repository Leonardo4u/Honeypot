from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass
class Stadium:
    stadium_id: str
    team: str
    capacity: int
    altitude_m: float
    surface: str
    roof: str
    city: str
    avg_attendance_pct: float = 0.85


@dataclass
class TravelInfo:
    distance_km: float
    timezone_diff_hours: float = 0.0
    days_since_last_match: int = 3
    matches_in_last_14_days: int = 2
    is_intercontinental: bool = False


@dataclass
class HAEstimate:
    team: str
    cluster_id: int
    ha_goals: float
    ha_win_prob: float
    confidence: float
    n_samples: int = 0


class StadiumClusterer:
    CLUSTER_PROFILES = {
        0: {"name": "fortress_atmospheric", "ha_multiplier": 1.45},
        1: {"name": "standard_home", "ha_multiplier": 1.0},
        2: {"name": "altitude_advantage", "ha_multiplier": 1.60},
        3: {"name": "modern_neutral", "ha_multiplier": 0.75},
        4: {"name": "small_ground_intimidator", "ha_multiplier": 1.20},
    }

    _CENTROIDS = [
        [0.00, 0.95, 0.92, 0.0, 0.5],
        [0.05, 0.55, 0.82, 0.1, 0.2],
        [0.60, 0.40, 0.88, 0.0, 0.0],
        [0.02, 0.75, 0.75, 0.5, 1.0],
        [0.02, 0.25, 0.90, 0.0, 0.0],
    ]

    def _featurize(self, stadium: Stadium) -> list[float]:
        surface_code = {"grass": 0.0, "hybrid": 0.5, "artificial": 1.0}.get(stadium.surface, 0.0)
        roof_code = {"open": 0.0, "partial": 0.5, "closed": 1.0}.get(stadium.roof, 0.0)
        return [
            min(1.0, stadium.altitude_m / 3000.0),
            min(1.0, stadium.capacity / 80000.0),
            stadium.avg_attendance_pct,
            surface_code,
            roof_code,
        ]

    @staticmethod
    def _euclidean(a: list[float], b: list[float]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def assign_cluster(self, stadium: Stadium) -> int:
        features = self._featurize(stadium)
        distances = [self._euclidean(features, c) for c in self._CENTROIDS]
        return distances.index(min(distances))


class HomeAwayDecomposer:
    BASE_HA_BY_CLUSTER = {0: 0.38, 1: 0.20, 2: 0.47, 3: 0.10, 4: 0.28}

    def __init__(
        self,
        travel_fatigue_per_1000km: float = 0.02,
        timezone_penalty_per_hour: float = 0.015,
        rest_bonus_per_day: float = 0.01,
        prior_weight_matches: int = 15,
    ) -> None:
        self.fatigue_per_1000km = travel_fatigue_per_1000km
        self.tz_penalty = timezone_penalty_per_hour
        self.rest_bonus = rest_bonus_per_day
        self.prior_weight = prior_weight_matches
        self.clusterer = StadiumClusterer()
        self._team_cluster_ha: dict[tuple[str, int], list[float]] = {}

    def register_match(self, home_team: str, home_stadium: Stadium, home_xg: float, away_xg: float) -> None:
        cluster = self.clusterer.assign_cluster(home_stadium)
        ha_observed = math.log(max(home_xg, 0.05) / max(away_xg, 0.05))
        key = (home_team, cluster)
        self._team_cluster_ha.setdefault(key, []).append(ha_observed)

    def estimate_ha(self, home_team: str, home_stadium: Stadium) -> HAEstimate:
        cluster = self.clusterer.assign_cluster(home_stadium)
        base_ha = self.BASE_HA_BY_CLUSTER.get(cluster, 0.20)
        key = (home_team, cluster)
        samples = self._team_cluster_ha.get(key, [])
        n = len(samples)

        if n > 0:
            observed = statistics.mean(samples)
            posterior = (n * observed + self.prior_weight * base_ha) / (n + self.prior_weight)
        else:
            posterior = base_ha

        confidence = min(1.0, n / 30.0)
        ha_goals = math.exp(posterior) - 1.0
        return HAEstimate(
            team=home_team,
            cluster_id=cluster,
            ha_goals=round(ha_goals, 4),
            ha_win_prob=round(posterior / 2.5, 4),
            confidence=round(confidence, 3),
            n_samples=n,
        )

    def travel_fatigue_penalty(self, travel: TravelInfo) -> float:
        dist_penalty = self.fatigue_per_1000km * (travel.distance_km / 1000.0)
        tz_penalty = self.tz_penalty * abs(travel.timezone_diff_hours)
        rest_diff = travel.days_since_last_match - 3
        rest_adj = -self.rest_bonus * max(-3, min(3, rest_diff))
        congestion = max(0, travel.matches_in_last_14_days - 3) * 0.015
        intercontinental = 0.08 if travel.is_intercontinental else 0.0
        total = dist_penalty + tz_penalty + rest_adj + congestion + intercontinental
        return round(max(0.0, total), 4)

    def adjusted_lambda_ratio(
        self,
        home_team: str,
        home_stadium: Stadium,
        away_travel: TravelInfo,
        base_lambda_home: float,
        base_lambda_away: float,
    ) -> dict:
        ha = self.estimate_ha(home_team, home_stadium)
        fat = self.travel_fatigue_penalty(away_travel)
        adj_home = math.exp(ha.ha_goals * 0.4)
        adj_away = math.exp(-fat)
        return {
            "lambda_home_base": round(base_lambda_home, 4),
            "lambda_away_base": round(base_lambda_away, 4),
            "lambda_home_adjusted": round(base_lambda_home * adj_home, 4),
            "lambda_away_adjusted": round(base_lambda_away * adj_away, 4),
            "ha_estimate": ha,
            "cluster_id": ha.cluster_id,
            "cluster_name": StadiumClusterer.CLUSTER_PROFILES[ha.cluster_id]["name"],
            "travel_fatigue": fat,
        }
