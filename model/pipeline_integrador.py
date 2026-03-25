from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Callable, Optional, Protocol

from module_01_sharp_money import MarketLine, OddsSnapshot, SharpMoneyDetector
from module_02_elo_xg import XGWeightedELO
from module_03_home_away import HomeAwayDecomposer, Stadium, TravelInfo
from module_04_hierarchical_bayes import HierarchicalBayesianModel
from module_05_06_07_weibull_zip_mc import MonteCarloSimulator, WeibullGoalModel, ZIPModel


logger = logging.getLogger(__name__)


class LambdaPredictor(Protocol):
    def predict_lambdas(self, home_team: str, away_team: str, division: str, country: str) -> dict:
        ...


class MatchProbabilityModel(Protocol):
    def match_probabilities(self, home_team: str, away_team: str) -> dict:
        ...


class LambdaAdjuster(Protocol):
    def adjusted_lambda_ratio(
        self,
        home_team: str,
        home_stadium: Stadium,
        away_travel: TravelInfo,
        base_lambda_home: float,
        base_lambda_away: float,
    ) -> dict:
        ...


class MarketModel(Protocol):
    def market_probs(self, lambda_home: float, lambda_away: float, is_derby: bool = False, weather_intensity: float = 0.0) -> dict:
        ...


class SharpScorer(Protocol):
    def sharp_score(self, line: MarketLine, our_odd: float, public_bet_pct: float = 0.5, peer_lines: Optional[list[MarketLine]] = None) -> dict:
        ...


class Simulator(Protocol):
    def run(self, lambda_home: float, lambda_away: float) -> dict:
        ...


@dataclass
class BetOpportunity:
    market: str
    our_probability: float
    market_odd: float
    implied_probability: float
    edge: float
    stake_fraction: float
    stake_units: float
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
        home_away_prior_weight_matches: int = 15,
        hbm: Optional[LambdaPredictor] = None,
        elo: Optional[MatchProbabilityModel] = None,
        ha_dec: Optional[LambdaAdjuster] = None,
        zip_m: Optional[MarketModel] = None,
        sharp: Optional[SharpScorer] = None,
        mc: Optional[Simulator] = None,
        diagnostic_hook: Optional[Callable[[dict], None]] = None,
        alert_hook: Optional[Callable[..., None]] = None,
    ) -> None:
        self.bankroll = bankroll
        self.max_kelly = max_kelly_fraction
        self.min_edge = min_edge_threshold
        self.min_sharp = min_sharp_score
        self.diagnostic_hook = diagnostic_hook
        self.alert_hook = alert_hook

        self.hbm = hbm or HierarchicalBayesianModel(use_xg_as_observation=True)
        self.elo = elo or XGWeightedELO(k_base=30.0, home_advantage=65.0, xg_blend=0.35)
        self.ha_dec = ha_dec or HomeAwayDecomposer(prior_weight_matches=home_away_prior_weight_matches)
        self.zip_m = zip_m or ZIPModel()
        self.sharp = sharp or SharpMoneyDetector(clv_edge_threshold=0.02)
        self.mc = mc or MonteCarloSimulator(n_simulations=mc_simulations, random_seed=42)

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
        confidence_home = float(pred.get("shrinkage_home", 0.5))
        confidence_away = float(pred.get("shrinkage_away", 0.5))
        lam_home = confidence_home * float(pred["lambda_home"]) + (1.0 - confidence_home) * base_lambda_home
        lam_away = confidence_away * float(pred["lambda_away"]) + (1.0 - confidence_away) * base_lambda_away

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
        try:
            lambdas = self.calibrated_lambdas(home_team, away_team, division, country, 1.35, 1.10)
            lambda_home = float(lambdas["lambda_home"])
            lambda_away = float(lambdas["lambda_away"])
        except Exception:
            logger.exception("calibrated_lambdas_failed", extra={"match_id": match_id})
            if self.alert_hook:
                try:
                    self.alert_hook(
                        "high",
                        "advanced_pipeline_lambda_fallback",
                        detalhes={
                            "match_id": match_id,
                            "home_team": home_team,
                            "away_team": away_team,
                            "division": division,
                            "country": country,
                        },
                    )
                except Exception:
                    logger.exception("alert_hook_failed", extra={"match_id": match_id})
            lambdas = {
                "hbm_shrinkage_home": 0.0,
                "hbm_shrinkage_away": 0.0,
                "ha_cluster": "fallback",
                "travel_fatigue": 0.0,
            }
            lambda_home = 1.35
            lambda_away = 1.10

        _weibull = WeibullGoalModel.from_poisson_lambdas(lambda_home, lambda_away)
        try:
            _zip = self.zip_m.market_probs(lambda_home, lambda_away, is_derby=is_derby, weather_intensity=weather_intensity)
        except Exception:
            logger.exception("zip_market_probs_failed", extra={"match_id": match_id})
            _zip = {"p_0_0": 0.0}

        try:
            mc = self.mc.run(lambda_home, lambda_away)
        except Exception:
            logger.exception("mc_run_failed", extra={"match_id": match_id})
            mc = {
                "p_home_win": 0.0,
                "p_draw": 0.0,
                "p_away_win": 0.0,
                "p_over_2_5": 0.0,
                "p_under_2_5": 1.0,
                "p_btts": 0.0,
                "top_scores": [],
            }

        try:
            elo_probs = self.elo.match_probabilities(home_team, away_team)
        except Exception:
            logger.exception("elo_match_probabilities_failed", extra={"match_id": match_id})
            elo_probs = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}

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
            stake_fraction = min(self.max_kelly, self.kelly_stake(float(p_model), float(odd), fraction=1.0))
            stake_units = max(0.0, self.bankroll * stake_fraction)

            line = MarketLine(
                match_id=match_id,
                market=market_key,
                selection=market_key,
                snapshots=[
                    OddsSnapshot(timestamp=datetime.now(UTC), odd=odd),
                    OddsSnapshot(timestamp=datetime.now(UTC), odd=odd),
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
                    stake_fraction=round(stake_fraction, 4),
                    stake_units=round(stake_units, 4),
                    sharp_score=float(sharp_score),
                    recommendation=rec,
                )
            )

        if self.diagnostic_hook:
            try:
                self.diagnostic_hook(
                    {
                        "match_id": match_id,
                        "lambda_home": lambda_home,
                        "lambda_away": lambda_away,
                        "shrinkage_home": lambdas.get("hbm_shrinkage_home", 0.0),
                        "shrinkage_away": lambdas.get("hbm_shrinkage_away", 0.0),
                        "opportunities": len(opportunities),
                    }
                )
            except Exception:
                logger.exception("diagnostic_hook_failed", extra={"match_id": match_id})

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
