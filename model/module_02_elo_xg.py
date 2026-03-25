from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MatchResult:
    match_id: str
    date: date
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    home_xg: float
    away_xg: float
    competition: str = ""
    neutral_venue: bool = False


@dataclass
class TeamRating:
    team: str
    overall: float = 1500.0
    home_bonus: float = 0.0
    away_penalty: float = 0.0
    n_matches: int = 0


class XGWeightedELO:
    def __init__(
        self,
        k_base: float = 30.0,
        home_advantage: float = 65.0,
        xg_blend: float = 0.35,
        recency_decay_days: float = 365.0,
        competition_weights: Optional[dict] = None,
        initial_rating: float = 1500.0,
    ) -> None:
        self.k_base = k_base
        self.home_adv = home_advantage
        self.xg_blend = xg_blend
        self.recency_decay = recency_decay_days
        self.initial_rating = initial_rating
        self.ratings: dict[str, TeamRating] = {}
        self.history: list[dict] = []
        self.competition_weights = competition_weights or {
            "premier_league": 1.0,
            "champions_league": 1.1,
            "default": 0.8,
        }

    def get_rating(self, team: str) -> TeamRating:
        if team not in self.ratings:
            self.ratings[team] = TeamRating(team=team, overall=self.initial_rating)
        return self.ratings[team]

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def match_probabilities(self, home_team: str, away_team: str) -> dict:
        home = self.get_rating(home_team)
        away = self.get_rating(away_team)
        e_home = self.expected_score(home.overall + self.home_adv, away.overall)
        rating_diff = abs((home.overall + self.home_adv) - away.overall)
        draw_prob = max(0.05, 0.25 - 0.0015 * rating_diff)
        home_prob = max(0.01, e_home - draw_prob / 2)
        away_prob = max(0.01, 1 - home_prob - draw_prob)
        total = home_prob + draw_prob + away_prob
        return {
            "home_win": round(home_prob / total, 4),
            "draw": round(draw_prob / total, 4),
            "away_win": round(away_prob / total, 4),
        }

    def _performance_factor(self, home_goals: int, away_goals: int, home_xg: float, away_xg: float) -> float:
        goal_diff = abs(home_goals - away_goals)
        xg_diff = home_xg - away_xg
        goal_factor = math.log(1 + goal_diff) + 1.0
        xg_factor = 1.0 + 0.4 * math.tanh(xg_diff / 1.5)
        return max(0.4, min(3.0, goal_factor * xg_factor))

    def _recency_factor(self, match_date: date, ref_date: date) -> float:
        days_ago = max(0, (ref_date - match_date).days)
        if days_ago == 0:
            return 1.0
        return math.exp(-math.log(2) * days_ago / self.recency_decay)

    def _competition_weight(self, competition: str) -> float:
        return self.competition_weights.get(competition.lower().replace(" ", "_"), self.competition_weights["default"])

    def _blended_score(self, home_goals: int, away_goals: int, home_xg: float, away_xg: float) -> tuple[float, float]:
        if home_goals > away_goals:
            base_home, base_away = 1.0, 0.0
        elif home_goals < away_goals:
            base_home, base_away = 0.0, 1.0
        else:
            base_home, base_away = 0.5, 0.5

        total_xg = home_xg + away_xg
        if total_xg > 0.1:
            xg_home = home_xg / total_xg
            xg_away = away_xg / total_xg
        else:
            xg_home, xg_away = 0.5, 0.5

        home = (1 - self.xg_blend) * base_home + self.xg_blend * xg_home
        away = (1 - self.xg_blend) * base_away + self.xg_blend * xg_away
        return home, away

    def update(self, match: MatchResult, reference_date: Optional[date] = None) -> dict:
        ref = reference_date or date.today()
        home = self.get_rating(match.home_team)
        away = self.get_rating(match.away_team)

        e_home = self.expected_score(home.overall + self.home_adv, away.overall)
        e_away = 1.0 - e_home
        s_home, s_away = self._blended_score(match.home_goals, match.away_goals, match.home_xg, match.away_xg)

        k_dynamic = self.k_base * self._performance_factor(match.home_goals, match.away_goals, match.home_xg, match.away_xg)
        k_dynamic *= self._recency_factor(match.date, ref) * self._competition_weight(match.competition)

        delta_home = k_dynamic * (s_home - e_home)
        delta_away = k_dynamic * (s_away - e_away)

        home.overall += delta_home
        away.overall += delta_away
        home.n_matches += 1
        away.n_matches += 1

        payload = {
            "k_dynamic": round(k_dynamic, 3),
            "delta_home": round(delta_home, 3),
            "delta_away": round(delta_away, 3),
            "new_home_rating": round(home.overall, 3),
            "new_away_rating": round(away.overall, 3),
        }
        self.history.append(payload)
        return payload
