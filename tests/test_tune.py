import csv
import os
import tempfile
import unittest

import tune


class TestTune(unittest.TestCase):
    def _write_csv(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_recommend_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "picks_log.csv")
            rows = []
            for i in range(30):
                rows.append(
                    {
                        "prediction_id": str(i),
                        "outcome": "1" if i % 2 == 0 else "0",
                        "calibrated_prob_model": "0.6" if i % 2 == 0 else "0.4",
                        "odds_at_pick": "2.0",
                        "kelly_stake": "10",
                        "confidence_dados": "70",
                        "edge_score": "80",
                    }
                )
            self._write_csv(path, rows)

            settled = tune.load_settled_rows(path)
            best, all_results = tune.recommend_threshold(
                settled,
                "confidence_floor",
                tune.CONF_CANDIDATES,
                extractor=lambda r: tune._to_float(r.get("confidence_dados"), 0.0),
                min_bets=20,
            )
            self.assertIsNotNone(best)
            self.assertTrue(len(all_results) >= 1)

    def test_apply_thresholds_regex(self):
        with tempfile.TemporaryDirectory() as td:
            model_dir = os.path.join(td, "model")
            os.makedirs(model_dir, exist_ok=True)
            edge_path = os.path.join(model_dir, "edge_score.py")
            analisar_path = os.path.join(model_dir, "analisar_jogo.py")

            with open(edge_path, "w", encoding="utf-8") as f:
                f.write(
                    "MIN_CONFIDENCE_ACTIONABLE = 64.0\n"
                    "def f(es, cf, floor, ev_v):\n"
                    "    if es >= 80.0 and cf >= floor and ev_v >= 0.02:\n"
                    "        return 'BET'\n"
                )
            with open(analisar_path, "w", encoding="utf-8") as f:
                f.write("def g(ev):\n    if ev < 0.04:\n        return 'x'\n")

            tune.apply_thresholds(
                td,
                {"ev_floor": 0.05, "confidence_floor": 68, "edge_cutoff": 85},
            )

            with open(edge_path, "r", encoding="utf-8") as f:
                edge_code = f.read()
            with open(analisar_path, "r", encoding="utf-8") as f:
                analisar_code = f.read()

            self.assertIn("MIN_CONFIDENCE_ACTIONABLE = 68.0", edge_code)
            self.assertIn("if es >= 85.0 and cf >= floor and ev_v >= 0.02:", edge_code)
            self.assertIn("if ev < 0.05:", analisar_code)


if __name__ == "__main__":
    unittest.main()
