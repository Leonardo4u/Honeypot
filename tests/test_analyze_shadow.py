import csv
import json
import os
import tempfile
import unittest

from scripts.analyze_shadow import build_report


class TestAnalyzeShadow(unittest.TestCase):
    def _write_jsonl(self, path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")

    def _write_picks(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _pick_row(self, pid, league, market, odds_pick, odds_close, outcome):
        return {
            "prediction_id": pid,
            "timestamp": "2026-04-01T12:00:00+00:00",
            "league": league,
            "market": market,
            "team_home": "A",
            "team_away": "B",
            "odds_at_pick": str(odds_pick),
            "implied_prob": "0.5",
            "raw_prob_model": "0.5",
            "calibrated_prob_model": "0.5",
            "calibrator_fitted": "True",
            "confidence_dados": "70",
            "estabilidade_odd": "70",
            "contexto_jogo": "70",
            "edge_score": "80",
            "kelly_fraction": "0.01",
            "kelly_stake": "10",
            "bank_used": "1000",
            "recomendacao_acao": "BET",
            "gate_reason": "",
            "outcome": str(outcome),
            "closing_odds": str(odds_close),
        }

    def test_healthy_verdict_promote(self):
        with tempfile.TemporaryDirectory() as td:
            shadow_path = os.path.join(td, "policy_v2_shadow.log")
            picks_path = os.path.join(td, "picks_log.csv")

            blocked = []
            picks = []
            for i in range(10):
                pid = f"b{i}"
                blocked.append(
                    {
                        "timestamp": "2026-04-01T10:00:00+00:00",
                        "prediction_id": pid,
                        "league": "Premier League",
                        "market": "1x2_casa",
                        "team_home": "A",
                        "team_away": "B",
                        "odds": 2.0,
                        "ev": 0.06,
                        "edge_score": 80,
                        "clv_estimate": -0.01,
                        "reject_reason": "steam contra",
                        "would_have_blocked": True,
                    }
                )
                # CLV bloqueado negativo
                picks.append(self._pick_row(pid, "Premier League", "1x2_casa", 2.0, 2.2, 0))

            for i in range(30):
                pid = f"p{i}"
                picks.append(self._pick_row(pid, "Premier League", "1x2_casa", 2.0, 2.05, 1))

            self._write_jsonl(shadow_path, blocked)
            self._write_picks(picks_path, picks)

            report = build_report(min_picks=20, shadow_log_path=shadow_path, picks_log_path=picks_path)
            self.assertEqual(report["verdict"], "PROMOTE")

    def test_wait_verdict_insufficient_picks(self):
        with tempfile.TemporaryDirectory() as td:
            shadow_path = os.path.join(td, "policy_v2_shadow.log")
            picks_path = os.path.join(td, "picks_log.csv")

            blocked = [
                {
                    "timestamp": "2026-04-01T10:00:00+00:00",
                    "prediction_id": "b1",
                    "league": "Serie A",
                    "market": "over_2.5",
                    "team_home": "A",
                    "team_away": "B",
                    "odds": 2.0,
                    "ev": 0.05,
                    "edge_score": 77,
                    "clv_estimate": -0.01,
                    "reject_reason": "ev baixo",
                    "would_have_blocked": True,
                }
            ]
            picks = [self._pick_row("b1", "Serie A", "over_2.5", 2.0, 1.95, 0)]

            self._write_jsonl(shadow_path, blocked)
            self._write_picks(picks_path, picks)

            report = build_report(min_picks=20, shadow_log_path=shadow_path, picks_log_path=picks_path)
            self.assertEqual(report["verdict"], "WAIT")

    def test_do_not_promote_when_blocked_clv_positive(self):
        with tempfile.TemporaryDirectory() as td:
            shadow_path = os.path.join(td, "policy_v2_shadow.log")
            picks_path = os.path.join(td, "picks_log.csv")

            blocked = []
            picks = []
            for i in range(10):
                pid = f"b{i}"
                blocked.append(
                    {
                        "timestamp": "2026-04-01T10:00:00+00:00",
                        "prediction_id": pid,
                        "league": "Bundesliga",
                        "market": "under_2.5",
                        "team_home": "A",
                        "team_away": "B",
                        "odds": 2.0,
                        "ev": 0.05,
                        "edge_score": 75,
                        "clv_estimate": 0.01,
                        "reject_reason": "steam contra",
                        "would_have_blocked": True,
                    }
                )
                # CLV bloqueado positivo -> bloqueando valor
                picks.append(self._pick_row(pid, "Bundesliga", "under_2.5", 2.0, 1.9, 0))

            for i in range(20):
                pid = f"p{i}"
                picks.append(self._pick_row(pid, "Bundesliga", "under_2.5", 2.0, 1.95, 1))

            self._write_jsonl(shadow_path, blocked)
            self._write_picks(picks_path, picks)

            report = build_report(min_picks=20, shadow_log_path=shadow_path, picks_log_path=picks_path)
            self.assertEqual(report["verdict"], "DO NOT PROMOTE")


if __name__ == "__main__":
    unittest.main()
