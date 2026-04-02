import os
import tempfile
import unittest
from unittest.mock import patch

from data import atualizar_stats


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"x"

    def json(self):
        return self._payload


class TestAtualizarStatsHistorico(unittest.TestCase):
    def _fixture_payload(self, season):
        rows = []
        # 60 jogos para passar gate minimo de 50.
        for i in range(60):
            rows.append(
                {
                    "fixture": {"date": f"{season}-05-{(i % 28) + 1:02d}T20:00:00+00:00"},
                    "teams": {
                        "home": {"name": f"Home {i}"},
                        "away": {"name": f"Away {i}"},
                    },
                    "goals": {"home": i % 3, "away": (i + 1) % 3},
                }
            )
        return {"paging": {"current": 1, "total": 1}, "response": rows}

    def test_fetch_historico_brasileirao_salva_csv(self):
        with tempfile.TemporaryDirectory() as td:
            old_key = atualizar_stats.API_FOOTBALL_KEY
            old_data_dir = atualizar_stats.BOT_DATA_DIR
            old_seasons = atualizar_stats._season_years

            atualizar_stats.API_FOOTBALL_KEY = "token"
            atualizar_stats.BOT_DATA_DIR = td
            atualizar_stats._season_years = lambda seasons_back=0: [2025]

            try:
                with patch("data.atualizar_stats.requests.get", return_value=_FakeResponse(payload=self._fixture_payload(2025))):
                    df = atualizar_stats.fetch_historico_brasileirao(seasons=0, league_id=71)

                self.assertGreaterEqual(len(df), 50)
                self.assertTrue(os.path.exists(os.path.join(td, "historico_BRA1.csv")))
                self.assertIn("time_casa", df[0])
                self.assertIn("gols_fora", df[0])
            finally:
                atualizar_stats.API_FOOTBALL_KEY = old_key
                atualizar_stats.BOT_DATA_DIR = old_data_dir
                atualizar_stats._season_years = old_seasons

    def test_fetch_historico_brasileirao_insufficient_matches(self):
        with tempfile.TemporaryDirectory() as td:
            old_key = atualizar_stats.API_FOOTBALL_KEY
            old_data_dir = atualizar_stats.BOT_DATA_DIR
            old_seasons = atualizar_stats._season_years

            atualizar_stats.API_FOOTBALL_KEY = "token"
            atualizar_stats.BOT_DATA_DIR = td
            atualizar_stats._season_years = lambda seasons_back=0: [2025]

            payload = {
                "paging": {"current": 1, "total": 1},
                "response": [
                    {
                        "fixture": {"date": "2025-05-10T20:00:00+00:00"},
                        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
                        "goals": {"home": 1, "away": 0},
                    }
                ],
            }

            try:
                with patch("data.atualizar_stats.requests.get", return_value=_FakeResponse(payload=payload)):
                    df = atualizar_stats.fetch_historico_brasileirao(seasons=0, league_id=71)

                self.assertEqual(len(df), 1)
                self.assertFalse(os.path.exists(os.path.join(td, "historico_BRA1.csv")))
            finally:
                atualizar_stats.API_FOOTBALL_KEY = old_key
                atualizar_stats.BOT_DATA_DIR = old_data_dir
                atualizar_stats._season_years = old_seasons

    def test_extract_fixture_rows_skips_none_goals_and_maps_fields(self):
        payload = {
            "response": [
                {
                    "fixture": {"date": "2024-05-01T20:00:00+00:00"},
                    "teams": {"home": {"name": "Flamengo"}, "away": {"name": "Palmeiras"}},
                    "goals": {"home": 2, "away": 1},
                },
                {
                    "fixture": {"date": "2024-05-02T20:00:00+00:00"},
                    "teams": {"home": {"name": "Corinthians"}, "away": {"name": "Santos"}},
                    "goals": {"home": None, "away": 0},
                },
            ]
        }

        rows = atualizar_stats._extract_fixture_rows(payload, "Brasileirao Serie A", 2024)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["time_casa"], "Flamengo")
        self.assertEqual(rows[0]["time_fora"], "Palmeiras")
        self.assertEqual(rows[0]["gols_casa"], 2)
        self.assertEqual(rows[0]["gols_fora"], 1)
        self.assertEqual(rows[0]["data_jogo"], "2024-05-01")


if __name__ == "__main__":
    unittest.main()
