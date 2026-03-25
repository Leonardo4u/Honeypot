from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency fallback
    np = None


@dataclass
class WeibullGoalModel:
    scale_home: float
    scale_away: float
    shape: float = 1.3
    match_duration: int = 90

    @classmethod
    def from_poisson_lambdas(cls, lambda_home: float, lambda_away: float, shape: float = 1.3, duration: int = 90) -> "WeibullGoalModel":
        scale_h = duration / (max(lambda_home, 1e-6) ** (1.0 / shape))
        scale_a = duration / (max(lambda_away, 1e-6) ** (1.0 / shape))
        return cls(scale_home=scale_h, scale_away=scale_a, shape=shape, match_duration=duration)

    def hazard_rate(self, t: float, is_home: bool) -> float:
        if t <= 0:
            return 0.0
        scale = self.scale_home if is_home else self.scale_away
        return (self.shape / scale) * ((t / scale) ** (self.shape - 1))

    def cumulative_expected_goals(self, t: float, is_home: bool) -> float:
        scale = self.scale_home if is_home else self.scale_away
        return (max(t, 0.0) / scale) ** self.shape

    def goals_in_window(self, t_start: float, t_end: float, is_home: bool) -> float:
        return max(0.0, self.cumulative_expected_goals(t_end, is_home) - self.cumulative_expected_goals(t_start, is_home))


class ZIPModel:
    def __init__(
        self,
        defensiveness_coef: float = 0.15,
        derby_bonus: float = 0.08,
        weather_coef: float = 0.05,
        base_zero_prob: float = 0.05,
    ) -> None:
        self.def_coef = defensiveness_coef
        self.derby_coef = derby_bonus
        self.weather_coef = weather_coef
        self.base_pi = base_zero_prob

    def _defensiveness_index(self, lambda_home: float, lambda_away: float) -> float:
        avg_lambda = (lambda_home + lambda_away) / 2.0
        return max(0.0, min(1.0, (2.0 - avg_lambda) / 1.5))

    def estimate_pi(self, lambda_home: float, lambda_away: float, is_derby: bool = False, weather_intensity: float = 0.0) -> float:
        def_idx = self._defensiveness_index(lambda_home, lambda_away)
        logit_pi = (
            math.log(self.base_pi / max(1.0 - self.base_pi, 1e-9))
            + self.def_coef * def_idx
            + self.derby_coef * float(is_derby)
            + self.weather_coef * weather_intensity
        )
        return 1.0 / (1.0 + math.exp(-logit_pi))

    def pmf(self, k: int, lam: float, pi: float) -> float:
        if k < 0:
            return 0.0
        if lam <= 0:
            poisson_pmf = 1.0 if k == 0 else 0.0
        else:
            poisson_log_pmf = -lam + (k * math.log(max(lam, 1e-12))) - math.lgamma(k + 1)
            poisson_pmf = math.exp(poisson_log_pmf)
        if k == 0:
            return pi + (1 - pi) * poisson_pmf
        return (1 - pi) * poisson_pmf

    def joint_score_probs(self, lambda_home: float, lambda_away: float, pi_home: float, pi_away: float, max_goals: int = 8) -> dict[tuple[int, int], float]:
        probs: dict[tuple[int, int], float] = {}
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                probs[(h, a)] = self.pmf(h, lambda_home, pi_home) * self.pmf(a, lambda_away, pi_away)
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}
        return probs

    def market_probs(self, lambda_home: float, lambda_away: float, is_derby: bool = False, weather_intensity: float = 0.0) -> dict:
        pi_home = self.estimate_pi(lambda_home, lambda_away, is_derby, weather_intensity)
        pi_away = pi_home * 0.8
        score_probs = self.joint_score_probs(lambda_home, lambda_away, pi_home, pi_away)
        p_00 = score_probs.get((0, 0), 0.0)
        p_btts = sum(v for (h, a), v in score_probs.items() if h > 0 and a > 0)
        p_over_15 = sum(v for (h, a), v in score_probs.items() if h + a > 1)
        p_over_25 = sum(v for (h, a), v in score_probs.items() if h + a > 2)
        return {
            "pi_home": round(pi_home, 4),
            "pi_away": round(pi_away, 4),
            "p_0_0": round(p_00, 4),
            "p_btts": round(p_btts, 4),
            "p_over_1_5": round(p_over_15, 4),
            "p_under_1_5": round(1 - p_over_15, 4),
            "p_over_2_5": round(p_over_25, 4),
            "p_under_2_5": round(1 - p_over_25, 4),
        }


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 50000, random_seed: Optional[int] = 42, weibull_shape: float = 1.3, dc_correction: bool = True) -> None:
        self.n_sims = n_simulations
        self.rng = random.Random(random_seed)
        self.rng_np = None
        if np is not None and hasattr(np, "random") and hasattr(np.random, "default_rng"):
            self.rng_np = np.random.default_rng(random_seed)
        self.shape = weibull_shape
        self.dc = dc_correction

    @staticmethod
    def _dc_correction(home_goals: int, away_goals: int, rho: float = -0.13) -> float:
        if home_goals == 0 and away_goals == 0:
            return 1 - rho
        if home_goals == 1 and away_goals == 0:
            return 1 + rho
        if home_goals == 0 and away_goals == 1:
            return 1 + rho
        if home_goals == 1 and away_goals == 1:
            return 1 - rho
        return 1.0

    def _simulate_one_match(self, lambda_home: float, lambda_away: float, minutes: int = 90) -> dict:
        home_goals = 0
        away_goals = 0
        goal_times_home: list[int] = []
        goal_times_away: list[int] = []
        weibull = WeibullGoalModel.from_poisson_lambdas(lambda_home, lambda_away, self.shape, minutes)

        for t in range(1, minutes + 1):
            rate_h = weibull.hazard_rate(float(t), True)
            rate_a = weibull.hazard_rate(float(t), False)
            if self.rng.random() < rate_h:
                home_goals += 1
                goal_times_home.append(t)
            if self.rng.random() < rate_a:
                away_goals += 1
                goal_times_away.append(t)

        dc_weight = self._dc_correction(home_goals, away_goals) if self.dc else 1.0
        return {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "goal_times_home": goal_times_home,
            "goal_times_away": goal_times_away,
            "dc_weight": dc_weight,
        }

    def run(self, lambda_home: float, lambda_away: float) -> dict:
        if self.rng_np is not None:
            return self._run_vectorized(lambda_home, lambda_away)

        results = [self._simulate_one_match(lambda_home, lambda_away) for _ in range(self.n_sims)]
        total_weight = sum(r["dc_weight"] for r in results)

        def weighted_prob(cond) -> float:
            return sum(r["dc_weight"] for r in results if cond(r)) / max(total_weight, 1e-9)

        score_counts: dict[tuple[int, int], float] = {}
        for r in results:
            key = (r["home_goals"], r["away_goals"])
            score_counts[key] = score_counts.get(key, 0.0) + r["dc_weight"]

        top_scores = sorted(score_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "p_home_win": round(weighted_prob(lambda r: r["home_goals"] > r["away_goals"]), 4),
            "p_draw": round(weighted_prob(lambda r: r["home_goals"] == r["away_goals"]), 4),
            "p_away_win": round(weighted_prob(lambda r: r["home_goals"] < r["away_goals"]), 4),
            "p_btts": round(weighted_prob(lambda r: r["home_goals"] > 0 and r["away_goals"] > 0), 4),
            "p_over_2_5": round(weighted_prob(lambda r: r["home_goals"] + r["away_goals"] > 2), 4),
            "p_under_2_5": round(weighted_prob(lambda r: r["home_goals"] + r["away_goals"] <= 2), 4),
            "top_scores": [(f"{h}-{a}", round(v / max(total_weight, 1e-9), 4)) for (h, a), v in top_scores],
        }

    def _run_vectorized(self, lambda_home: float, lambda_away: float, minutes: int = 90) -> dict:
        weibull = WeibullGoalModel.from_poisson_lambdas(lambda_home, lambda_away, self.shape, minutes)
        t = np.arange(1.0, float(minutes) + 1.0)

        rates_home = np.clip(np.array([weibull.hazard_rate(float(x), True) for x in t]), 0.0, 1.0)
        rates_away = np.clip(np.array([weibull.hazard_rate(float(x), False) for x in t]), 0.0, 1.0)

        home_goals = (self.rng_np.random((self.n_sims, minutes)) < rates_home).sum(axis=1).astype(int)
        away_goals = (self.rng_np.random((self.n_sims, minutes)) < rates_away).sum(axis=1).astype(int)

        if self.dc:
            rho = -0.13
            dc_weights = np.ones(self.n_sims, dtype=float)
            mask_00 = (home_goals == 0) & (away_goals == 0)
            mask_10 = (home_goals == 1) & (away_goals == 0)
            mask_01 = (home_goals == 0) & (away_goals == 1)
            mask_11 = (home_goals == 1) & (away_goals == 1)
            dc_weights[mask_00 | mask_11] -= rho
            dc_weights[mask_10 | mask_01] += rho
        else:
            dc_weights = np.ones(self.n_sims, dtype=float)

        total_weight = float(dc_weights.sum())
        denom = max(total_weight, 1e-9)

        def weighted_prob(mask):
            return float(dc_weights[mask].sum() / denom)

        pairs = np.column_stack((home_goals, away_goals))
        unique_pairs, inverse = np.unique(pairs, axis=0, return_inverse=True)
        weighted_counts = np.bincount(inverse, weights=dc_weights)
        order = np.argsort(weighted_counts)[::-1][:10]
        top_scores = [
            (f"{int(unique_pairs[i, 0])}-{int(unique_pairs[i, 1])}", round(float(weighted_counts[i] / denom), 4))
            for i in order
        ]

        return {
            "p_home_win": round(weighted_prob(home_goals > away_goals), 4),
            "p_draw": round(weighted_prob(home_goals == away_goals), 4),
            "p_away_win": round(weighted_prob(home_goals < away_goals), 4),
            "p_btts": round(weighted_prob((home_goals > 0) & (away_goals > 0)), 4),
            "p_over_2_5": round(weighted_prob((home_goals + away_goals) > 2), 4),
            "p_under_2_5": round(weighted_prob((home_goals + away_goals) <= 2), 4),
            "top_scores": top_scores,
        }
