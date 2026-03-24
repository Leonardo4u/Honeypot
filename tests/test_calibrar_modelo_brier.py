import io
import unittest
from contextlib import redirect_stdout

import pandas as pd

import calibrar_modelo as calibrador
import poisson
import xg_understat


class TestCalibrarModeloBrier(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            [
                {"liga": "Premier League", "time_casa": "A", "time_fora": "B", "gols_casa": 2, "gols_fora": 1},
                {"liga": "Premier League", "time_casa": "C", "time_fora": "D", "gols_casa": 1, "gols_fora": 1},
                {"liga": "La Liga", "time_casa": "E", "time_fora": "F", "gols_casa": 0, "gols_fora": 1},
                {"liga": "La Liga", "time_casa": "G", "time_fora": "H", "gols_casa": 3, "gols_fora": 0},
                {"liga": "Serie A", "time_casa": "I", "time_fora": "J", "gols_casa": 2, "gols_fora": 2},
                {"liga": "Serie A", "time_casa": "K", "time_fora": "L", "gols_casa": 1, "gols_fora": 0},
            ]
        )

    def test_brier_reprodutivel_mesma_seed(self):
        old_xg = xg_understat.calcular_media_gols_com_xg
        old_prob = poisson.calcular_probabilidades

        def fake_xg(*_args, **_kwargs):
            return 1.3, 0.9, "medias"

        def fake_prob(*_args, **_kwargs):
            return {"prob_casa": 0.6, "prob_empate": 0.25, "prob_fora": 0.15}

        xg_understat.calcular_media_gols_com_xg = fake_xg
        poisson.calcular_probabilidades = fake_prob

        try:
            out1 = io.StringIO()
            with redirect_stdout(out1):
                r1 = calibrador.calcular_brier_historico(self.df, n_amostras=5, random_state=42)

            out2 = io.StringIO()
            with redirect_stdout(out2):
                r2 = calibrador.calcular_brier_historico(self.df, n_amostras=5, random_state=42)

            self.assertEqual(r1, r2)
            self.assertIn("Sem dados xG (usou medias):", out1.getvalue())
            self.assertEqual(r1["seed"], 42)
            self.assertGreater(r1["jogos_processados"], 0)
        finally:
            xg_understat.calcular_media_gols_com_xg = old_xg
            poisson.calcular_probabilidades = old_prob

    def test_brier_expoe_metricas_fallback(self):
        old_xg = xg_understat.calcular_media_gols_com_xg
        old_prob = poisson.calcular_probabilidades

        def fake_xg(*_args, **_kwargs):
            return 1.0, 1.0, "médias"

        def fake_prob(*_args, **_kwargs):
            return {"prob_casa": 0.55, "prob_empate": 0.25, "prob_fora": 0.20}

        xg_understat.calcular_media_gols_com_xg = fake_xg
        poisson.calcular_probabilidades = fake_prob

        try:
            result = calibrador.calcular_brier_historico(self.df, n_amostras=4, random_state=42)
            self.assertEqual(result["sem_xg"], result["jogos_processados"])
            self.assertEqual(result["sem_xg_pct"], 100.0)
            self.assertIn("classificacao", result)
            self.assertIn("brier_score", result)
        finally:
            xg_understat.calcular_media_gols_com_xg = old_xg
            poisson.calcular_probabilidades = old_prob


if __name__ == "__main__":
    unittest.main()
