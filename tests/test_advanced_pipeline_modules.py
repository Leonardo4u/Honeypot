import unittest
from datetime import UTC, datetime, date
import os
import tempfile

from model.module_01_sharp_money import CLVTracker, SharpMoneyDetector, MarketLine, OddsSnapshot
from model.module_02_elo_xg import XGWeightedELO, MatchResult
from model.module_03_home_away import HomeAwayDecomposer, Stadium, TravelInfo
from model.module_04_hierarchical_bayes import HierarchicalBayesianModel
from model.module_05_06_07_weibull_zip_mc import WeibullGoalModel, ZIPModel, MonteCarloSimulator
from model.pipeline_integrador import BettingPipeline


class TestAdvancedPipelineModules(unittest.TestCase):
    def test_sharp_money_basic(self):
        detector = SharpMoneyDetector()
        line = MarketLine(
            match_id="m1",
            market="home",
            selection="home",
            snapshots=[
                OddsSnapshot(timestamp=datetime.now(UTC), odd=2.10),
                OddsSnapshot(timestamp=datetime.now(UTC), odd=2.00),
            ],
        )
        score = detector.sharp_score(line, our_odd=2.05)
        self.assertIn("sharp_score", score)

    def test_sharp_money_overround_dinamico(self):
        detector = SharpMoneyDetector()
        open_odds = {"home": 2.10, "draw": 3.30, "away": 3.60}
        close_odds = {"home": 2.00, "draw": 3.20, "away": 4.00}
        over_open = detector.estimate_overround(open_odds)
        over_close = detector.estimate_overround(close_odds)
        clv = detector.closing_line_value(2.10, 2.00, over_open, over_close)
        self.assertGreaterEqual(over_open, 1.0)
        self.assertGreaterEqual(over_close, 1.0)
        self.assertIsInstance(clv, float)

    def test_clv_tracker_summary_vazio_e_record(self):
        tracker = CLVTracker()
        self.assertEqual(tracker.summary(), {})
        tracker.record("b1", bet_odd=2.10, close_odd=2.00, stake=2.0)
        summary = tracker.summary()
        self.assertEqual(summary.get("n_bets"), 1)
        self.assertIn("mean_clv", summary)

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

    def test_pipeline_integrador_graceful_degradation(self):
        class BrokenMC:
            def run(self, lambda_home, lambda_away):
                raise RuntimeError("sim error")

        pipe = BettingPipeline(mc=BrokenMC())
        result = pipe.analyze_match(
            match_id="m4",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 2.0, "away": 3.4},
        )
        self.assertIn("model_probs", result)
        self.assertIn("top_scores", result)

    def test_pipeline_integrador_diagnostic_hook_called(self):
        called = []

        def hook(payload):
            called.append(payload)

        pipe = BettingPipeline(mc_simulations=100, diagnostic_hook=hook)
        result = pipe.analyze_match(
            match_id="m5",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 2.1, "away": 3.2},
        )
        self.assertIn("model_probs", result)
        self.assertGreaterEqual(len(called), 1)
        self.assertEqual(called[0]["match_id"], "m5")

    def test_pipeline_integrador_diagnostic_hook_failure_no_propagate(self):
        def broken_hook(_payload):
            raise RuntimeError("broken hook")

        pipe = BettingPipeline(mc_simulations=100, diagnostic_hook=broken_hook)
        result = pipe.analyze_match(
            match_id="m6",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 2.1, "away": 3.2},
        )
        self.assertIn("model_probs", result)

    def test_pipeline_integrador_inclui_kelly_stake(self):
        pipe = BettingPipeline(mc_simulations=100)
        result = pipe.analyze_match(
            match_id="m7",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 10.0, "away": 10.0, "under_2.5": 10.0},
        )
        if result["opportunities"]:
            op = result["opportunities"][0]
            self.assertTrue(hasattr(op, "stake_fraction"))
            self.assertTrue(hasattr(op, "stake_units"))

    def test_pipeline_integrador_alert_hook_on_lambda_fallback(self):
        class BrokenHBM:
            def predict_lambdas(self, *_args, **_kwargs):
                raise RuntimeError("hbm fail")

        captured = []

        def alert_hook(severidade, codigo, detalhes=None):
            captured.append((severidade, codigo, detalhes))

        pipe = BettingPipeline(hbm=BrokenHBM(), alert_hook=alert_hook)
        result = pipe.analyze_match(
            match_id="m8",
            home_team="A",
            away_team="B",
            division="Premier League",
            country="England",
            market_odds={"home": 2.0, "away": 3.4},
        )
        self.assertIn("model_probs", result)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], "high")
        self.assertEqual(captured[0][1], "advanced_pipeline_lambda_fallback")

    def test_model_state_persistence_roundtrip(self):
        elo = XGWeightedELO()
        elo.update(
            MatchResult(
                match_id="m8",
                date=date.today(),
                home_team="A",
                away_team="B",
                home_goals=1,
                away_goals=0,
                home_xg=1.2,
                away_xg=0.7,
                competition="premier_league",
            )
        )
        hbm = HierarchicalBayesianModel()
        hbm.update("A", "B", 1, 0, 1.2, 0.7, "Premier League", "England")

        with tempfile.TemporaryDirectory(prefix="model-state-") as tmp:
            elo_path = os.path.join(tmp, "elo.json")
            hbm_path = os.path.join(tmp, "hbm.json")
            elo.save(elo_path)
            hbm.save(hbm_path)
            elo_loaded = XGWeightedELO.load(elo_path)
            hbm_loaded = HierarchicalBayesianModel.load(hbm_path)

        self.assertIn("A", elo_loaded.ratings)
        self.assertIn("A", hbm_loaded.teams)


if __name__ == "__main__":
    unittest.main()
