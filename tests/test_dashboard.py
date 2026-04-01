import csv
import os
import tempfile
import unittest

import dashboard


class TestDashboard(unittest.TestCase):
    def _write_rows(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_reliability_and_group_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "picks_log.csv")
            rows = [
                {
                    "prediction_id": "1",
                    "timestamp": "t",
                    "league": "L",
                    "market": "M",
                    "team_home": "A",
                    "team_away": "B",
                    "odds_at_pick": "2.0",
                    "implied_prob": "0.5",
                    "raw_prob_model": "0.6",
                    "calibrated_prob_model": "0.6",
                    "calibrator_fitted": "True",
                    "confidence_dados": "70",
                    "estabilidade_odd": "70",
                    "contexto_jogo": "70",
                    "edge_score": "80",
                    "kelly_fraction": "0.02",
                    "kelly_stake": "10",
                    "bank_used": "1000",
                    "recomendacao_acao": "BET",
                    "gate_reason": "",
                    "outcome": "1",
                    "closing_odds": "1.9",
                },
                {
                    "prediction_id": "2",
                    "timestamp": "t",
                    "league": "L",
                    "market": "M",
                    "team_home": "C",
                    "team_away": "D",
                    "odds_at_pick": "2.0",
                    "implied_prob": "0.5",
                    "raw_prob_model": "0.4",
                    "calibrated_prob_model": "0.4",
                    "calibrator_fitted": "True",
                    "confidence_dados": "65",
                    "estabilidade_odd": "65",
                    "contexto_jogo": "65",
                    "edge_score": "75",
                    "kelly_fraction": "0.01",
                    "kelly_stake": "10",
                    "bank_used": "1000",
                    "recomendacao_acao": "BET",
                    "gate_reason": "",
                    "outcome": "0",
                    "closing_odds": "2.1",
                },
            ]
            self._write_rows(path, rows)

            loaded = dashboard.load_rows(path)
            settled = dashboard.settled_rows(loaded)
            self.assertEqual(len(settled), 2)

            groups = dashboard._group_metrics(settled)
            self.assertEqual(groups["BET"]["n"], 2)
            self.assertGreaterEqual(groups["BET"]["brier"], 0.0)

            rel = dashboard.reliability_by_bucket(settled, n_buckets=10)
            self.assertEqual(len(rel), 10)


if __name__ == "__main__":
    unittest.main()
