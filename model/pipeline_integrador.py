from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from module_01_sharp_money import MarketLine, OddsSnapshot, SharpMoneyDetector
from module_02_elo_xg import XGWeightedELO
from module_03_home_away import HomeAwayDecomposer, Stadium, TravelInfo
from module_04_hierarchical_bayes import HierarchicalBayesianModel
from module_05_06_07_weibull_zip_mc import MonteCarloSimulator, WeibullGoalModel, ZIPModel


@dataclass
class BetOpportunity:
    market: str
    our_probability: float
    market_odd: float
    implied_probability: float
    edge: float
    sharp_score: float
    recommendation: str


class BettingPipeline:
    def __init__(
        self,
        bankroll: float = 10000.0,
        max_kelly_fraction: float = 0.25,
        min_edge_threshold: float = 0.03,
        min_sharp_score: float = 0.30,
        mc_simulations: int = 10000,
    ) -> None:
        self.bankroll = bankroll
        self.max_kelly = max_kelly_fraction
        self.min_edge = min_edge_threshold
        self.min_sharp = min_sharp_score

        self.hbm = HierarchicalBayesianModel(use_xg_as_observation=True)
        self.elo = XGWeightedELO(k_base=30.0, home_advantage=65.0, xg_blend=0.35)
        self.ha_dec = HomeAwayDecomposer()
        self.zip_m = ZIPModel()
        self.sharp = SharpMoneyDetector(clv_edge_threshold=0.02)
        self.mc = MonteCarloSimulator(n_simulations=mc_simulations, random_seed=42)

    @staticmethod
    def remove_overround(odds: dict[str, float]) -> dict[str, float]:
        raw = {k: 1.0 / max(v, 1e-9) for k, v in odds.items()}
        total = sum(raw.values())
        if total <= 0:
            return {k: 0.0 for k in odds}
        return {k: p / total for k, p in raw.items()}

    @staticmethod
    def kelly_stake(p_model: float, odd: float, fraction: float = 0.25) -> float:
        b = odd - 1.0
        if b <= 0:
            return 0.0
        q = 1.0 - p_model
        full = (b * p_model - q) / b
        return max(0.0, full * fraction)

    def calibrated_lambdas(
        self,
        home_team: str,
        away_team: str,
        division: str,
        country: str,
        base_lambda_home: float,
        base_lambda_away: float,
        stadium: Optional[Stadium] = None,
        travel: Optional[TravelInfo] = None,
    ) -> dict:
        pred = self.hbm.predict_lambdas(home_team, away_team, division, country)
        lam_home = (pred["lambda_home"] + base_lambda_home) / 2.0
        lam_away = (pred["lambda_away"] + base_lambda_away) / 2.0

        if stadium is None:
            stadium = Stadium(
                stadium_id=f"{home_team}_default",
                team=home_team,
                capacity=35000,
                altitude_m=100.0,
                surface="grass",
                roof="open",
                city="unknown",
                avg_attendance_pct=0.85,
            )
        if travel is None:
            travel = TravelInfo(distance_km=350.0, timezone_diff_hours=0.0, days_since_last_match=3, matches_in_last_14_days=2)

        ha_result = self.ha_dec.adjusted_lambda_ratio(home_team, stadium, travel, lam_home, lam_away)
        return {
            "lambda_home": ha_result["lambda_home_adjusted"],
            "lambda_away": ha_result["lambda_away_adjusted"],
            "hbm_shrinkage_home": pred["shrinkage_home"],
            "hbm_shrinkage_away": pred["shrinkage_away"],
            "ha_cluster": ha_result["cluster_name"],
            "travel_fatigue": ha_result["travel_fatigue"],
        }

    def analyze_match(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        division: str,
        country: str,
        market_odds: dict[str, float],
        is_derby: bool = False,
        weather_intensity: float = 0.0,
    ) -> dict:
        lambdas = self.calibrated_lambdas(home_team, away_team, division, country, 1.35, 1.10)
        lambda_home = lambdas["lambda_home"]
        lambda_away = lambdas["lambda_away"]

        _weibull = WeibullGoalModel.from_poisson_lambdas(lambda_home, lambda_away)
        _zip = self.zip_m.market_probs(lambda_home, lambda_away, is_derby=is_derby, weather_intensity=weather_intensity)
        mc = self.mc.run(lambda_home, lambda_away)
        elo_probs = self.elo.match_probabilities(home_team, away_team)

        model_probs = {
            "home": mc["p_home_win"],
            "draw": mc["p_draw"],
            "away": mc["p_away_win"],
            "over_2.5": mc["p_over_2_5"],
            "under_2.5": mc["p_under_2_5"],
            "btts_yes": mc["p_btts"],
            "p_0_0": _zip["p_0_0"],
        }

        fair_probs = self.remove_overround(market_odds)
        opportunities: list[BetOpportunity] = []

        for market_key, odd in market_odds.items():
            if market_key not in model_probs:
                continue
            p_model = model_probs[market_key]
            p_market = fair_probs.get(market_key, 1.0 / max(odd, 1e-9))
            edge = p_model - p_market
            if edge < self.min_edge:
                continue

            line = MarketLine(
                match_id=match_id,
                market=market_key,
                selection=market_key,
                snapshots=[
                    OddsSnapshot(timestamp=datetime.utcnow(), odd=odd),
                    OddsSnapshot(timestamp=datetime.utcnow(), odd=odd),
                ],
            )
            sharp_score = self.sharp.sharp_score(line, our_odd=odd).get("sharp_score", 0.0)
            rec = "STRONG" if edge > 0.05 and sharp_score > self.min_sharp else "MEDIUM" if edge > 0.03 else "SMALL"
            opportunities.append(
                BetOpportunity(
                    market=market_key,
                    our_probability=round(p_model, 4),
                    market_odd=odd,
                    implied_probability=round(p_market, 4),
                    edge=round(edge, 4),
                    sharp_score=float(sharp_score),
                    recommendation=rec,
                )
            )

        return {
            "match_id": match_id,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "model_probs": model_probs,
            "elo_probs": elo_probs,
            "top_scores": mc["top_scores"][:5],
            "opportunities": opportunities,
            "hbm_shrinkage_home": lambdas["hbm_shrinkage_home"],
            "hbm_shrinkage_away": lambdas["hbm_shrinkage_away"],
        }
