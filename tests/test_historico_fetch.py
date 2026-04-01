import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import pandas as pd

import calibrar_modelo


class TestHistoricoFetch(unittest.TestCase):
    def _sample_df(self):
        return pd.DataFrame(
            [
                {"HomeTeam": "Arsenal", "AwayTeam": "Chelsea", "FTHG": 1, "FTAG": 0, "Date": "01/01/2025"},
                {"HomeTeam": "Arsenal", "AwayTeam": "Chelsea", "FTHG": 1, "FTAG": 0, "Date": "01/01/2025"},
                {"HomeTeam": "Liverpool", "AwayTeam": "Tottenham", "FTHG": 2, "FTAG": 2, "Date": "02/01/2025"},
            ]
        )

    def test_multi_season_merge_and_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            old_data = calibrar_modelo.BOT_DATA_DIR
            old_hist = calibrar_modelo.HISTORICO_DIR
            old_map = calibrar_modelo.LIGAS_FOOTBALL_DATA
            old_sleep = calibrar_modelo.time.sleep
            old_dl = calibrar_modelo._download_csv_with_retry
            old_seasons = calibrar_modelo._season_codes
            try:
                calibrar_modelo.BOT_DATA_DIR = td
                calibrar_modelo.HISTORICO_DIR = os.path.join(td, "historico")
                calibrar_modelo.LIGAS_FOOTBALL_DATA = {"Premier League": "E0"}
                calibrar_modelo._season_codes = lambda _n=3: ["2425", "2324"]
                calibrar_modelo.time.sleep = lambda *_args, **_kwargs: None

                def fake_download(_url, attempts=3, backoff_seconds=0.8):
                    return self._sample_df(), "ok", None

                calibrar_modelo._download_csv_with_retry = fake_download

                result = calibrar_modelo.fetch_history_multi_season(seasons_back=1)
                merged = result["merged_by_code"]["E0"]
                # 2 temporadas x 3 linhas, com duplicata interna removida por temporada e dedup global.
                self.assertEqual(len(merged), 2)
                out_path = os.path.join(td, "historico_E0.csv")
                self.assertTrue(os.path.exists(out_path))
            finally:
                calibrar_modelo.BOT_DATA_DIR = old_data
                calibrar_modelo.HISTORICO_DIR = old_hist
                calibrar_modelo.LIGAS_FOOTBALL_DATA = old_map
                calibrar_modelo.time.sleep = old_sleep
                calibrar_modelo._download_csv_with_retry = old_dl
                calibrar_modelo._season_codes = old_seasons

    def test_404_skip_behavior(self):
        with tempfile.TemporaryDirectory() as td:
            old_data = calibrar_modelo.BOT_DATA_DIR
            old_hist = calibrar_modelo.HISTORICO_DIR
            old_map = calibrar_modelo.LIGAS_FOOTBALL_DATA
            old_sleep = calibrar_modelo.time.sleep
            old_dl = calibrar_modelo._download_csv_with_retry
            old_seasons = calibrar_modelo._season_codes
            try:
                calibrar_modelo.BOT_DATA_DIR = td
                calibrar_modelo.HISTORICO_DIR = os.path.join(td, "historico")
                calibrar_modelo.LIGAS_FOOTBALL_DATA = {"Premier League": "E0"}
                calibrar_modelo._season_codes = lambda _n=3: ["2425", "2324"]
                calibrar_modelo.time.sleep = lambda *_args, **_kwargs: None

                calls = {"n": 0}

                def fake_download(_url, attempts=3, backoff_seconds=0.8):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        return self._sample_df(), "ok", None
                    return None, "not_found", None

                calibrar_modelo._download_csv_with_retry = fake_download

                result = calibrar_modelo.fetch_history_multi_season(seasons_back=1)
                info = result["report"]["E0"]
                self.assertIn("404", " ".join(info.get("warnings", [])))
                self.assertEqual(info["total_matches"], 2)
            finally:
                calibrar_modelo.BOT_DATA_DIR = old_data
                calibrar_modelo.HISTORICO_DIR = old_hist
                calibrar_modelo.LIGAS_FOOTBALL_DATA = old_map
                calibrar_modelo.time.sleep = old_sleep
                calibrar_modelo._download_csv_with_retry = old_dl
                calibrar_modelo._season_codes = old_seasons

    def test_check_coverage_output_format(self):
        coverage = {
            "per_league": {
                "E0": {
                    "league": "Premier League",
                    "mean_n": 42.0,
                    "teams": {"Arsenal": 60, "Chelsea": 30},
                }
            },
            "mean_n_per_team": 45.0,
            "leagues_all_teams_n50": [],
        }
        out = io.StringIO()
        with redirect_stdout(out):
            calibrar_modelo.print_coverage_report(coverage, min_n=50)
        txt = out.getvalue()
        self.assertIn("[Premier League|E0]", txt)
        self.assertIn("Arsenal: n=60 [OK]", txt)
        self.assertIn("Chelsea: n=30 [INSUFFICIENT]", txt)

    def test_wrong_league_detection_rejects_file(self):
        with tempfile.TemporaryDirectory() as td:
            old_data = calibrar_modelo.BOT_DATA_DIR
            old_hist = calibrar_modelo.HISTORICO_DIR
            old_map = calibrar_modelo.LIGAS_FOOTBALL_DATA
            old_sleep = calibrar_modelo.time.sleep
            old_dl = calibrar_modelo._download_csv_with_retry
            old_seasons = calibrar_modelo._season_codes
            try:
                calibrar_modelo.BOT_DATA_DIR = td
                calibrar_modelo.HISTORICO_DIR = os.path.join(td, "historico")
                calibrar_modelo.LIGAS_FOOTBALL_DATA = {"Premier League": "E0"}
                calibrar_modelo._season_codes = lambda _n=3: ["2425"]
                calibrar_modelo.time.sleep = lambda *_args, **_kwargs: None

                wrong_df = pd.DataFrame(
                    [
                        {"HomeTeam": "Genk", "AwayTeam": "Gent", "FTHG": 1, "FTAG": 0, "Date": "01/01/2025"},
                        {"HomeTeam": "Anderlecht", "AwayTeam": "Standard Liege", "FTHG": 2, "FTAG": 1, "Date": "02/01/2025"},
                        {"HomeTeam": "Club Brugge", "AwayTeam": "Antwerp", "FTHG": 0, "FTAG": 0, "Date": "03/01/2025"},
                    ]
                )

                calibrar_modelo._download_csv_with_retry = lambda *_args, **_kwargs: (wrong_df, "ok", None)
                result = calibrar_modelo.fetch_history_multi_season(seasons_back=0)

                self.assertNotIn("E0", result["merged_by_code"])
                warnings = " ".join(result["report"]["E0"].get("warnings", []))
                self.assertIn("WRONG DATA", warnings)
                self.assertFalse(os.path.exists(os.path.join(td, "historico_E0.csv")))
            finally:
                calibrar_modelo.BOT_DATA_DIR = old_data
                calibrar_modelo.HISTORICO_DIR = old_hist
                calibrar_modelo.LIGAS_FOOTBALL_DATA = old_map
                calibrar_modelo.time.sleep = old_sleep
                calibrar_modelo._download_csv_with_retry = old_dl
                calibrar_modelo._season_codes = old_seasons


if __name__ == "__main__":
    unittest.main()
