import unittest
from datetime import datetime, date
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_DIR = os.path.join(ROOT, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

from module_01_sharp_money import SharpMoneyDetector, MarketLine, OddsSnapshot
from module_02_elo_xg import XGWeightedELO, MatchResult
from module_03_home_away import HomeAwayDecomposer, Stadium, TravelInfo
from module_04_hierarchical_bayes import HierarchicalBayesianModel
from module_05_06_07_weibull_zip_mc import WeibullGoalModel, ZIPModel, MonteCarloSimulator
from pipeline_integrador import BettingPipeline


class TestAdvancedPipelineModules(unittest.TestCase):
    def test_sharp_money_basic(self):
        detector = SharpMoneyDetector()
        line = MarketLine(
            match_id="m1",
            market="home",
            selection="home",
            snapshots=[
                OddsSnapshot(timestamp=datetime.utcnow(), odd=2.10),
                OddsSnapshot(timestamp=datetime.utcnow(), odd=2.00),
            ],
        )
        score = detector.sharp_score(line, our_odd=2.05)
        self.assertIn("sharp_score", score)

    def test_elo_update_and_probs(self):
        elo = XGWeightedELO()
        before = elo.match_probabilities("A", "B")
        self.assertIn("home_win", before)
        elo.update(
            MatchResult(
                match_id="m2",
                date=date.today(),
                home_team="A",
                away_team="B",
                home_goals=2,
                away_goals=1,
                home_xg=1.9,
                away_xg=0.8,
                competition="premier_league",
            )
        )
        after = elo.match_probabilities("A", "B")
        self.assertIn("home_win", after)

    def test_home_away_adjustment(self):
        dec = HomeAwayDecomposer()
        st = Stadium("s1", "A", 50000, 100.0, "grass", "open", "X", 0.9)
        tr = TravelInfo(distance_km=1200, timezone_diff_hours=1.0, days_since_last_match=2)
        dec.register_match("A", st, 1.8, 0.7)
        result = dec.adjusted_lambda_ratio("A", st, tr, 1.4, 1.1)
        self.assertIn("lambda_home_adjusted", result)

    def test_hbm_predict(self):
        hbm = HierarchicalBayesianModel()
        hbm.update("A", "B", 2, 1, 1.9, 0.9, "Premier League", "England")
        pred = hbm.predict_lambdas("A", "B", "Premier League", "England")
        self.assertIn("lambda_home", pred)

    def test_weibull_zip_mc(self):
        weib = WeibullGoalModel.from_poisson_lambdas(1.5, 1.1)
        self.assertGreaterEqual(weib.hazard_rate(45, True), 0.0)
        zip_m = ZIPModel()
        zip_probs = zip_m.market_probs(1.5, 1.1)
        self.assertIn("p_0_0", zip_probs)
        mc = MonteCarloSimulator(n_simulations=500, random_seed=7)
        out = mc.run(1.5, 1.1)
        self.assertIn("p_home_win", out)

    def test_pipeline_integrador(self):
        pipe = BettingPipeline(mc_simulations=500)
        # Warm up HBM with one historical update
        pipe.hbm.update("A", "B", 2, 1, 1.8, 0.9, "Premier League", "England")
        result = pipe.analyze_match(
            match_id="m3",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 2.0, "away": 3.4, "over_2.5": 1.9, "under_2.5": 1.95},
        )
        self.assertIn("model_probs", result)


if __name__ == "__main__":
    unittest.main()
