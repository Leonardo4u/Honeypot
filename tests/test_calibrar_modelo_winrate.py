import io
import unittest
from contextlib import redirect_stdout

import pandas as pd

import calibrar_modelo as calibrador
import poisson
import xg_understat


class TestCalibrarModeloWinRate(unittest.TestCase):
    def _patch_dependencies(self):
        old_xg = xg_understat.calcular_media_gols_com_xg
        old_prob = poisson.calcular_probabilidades
        old_ou = poisson.calcular_prob_over_under

        def fake_xg(*_args, **_kwargs):
            return 1.4, 1.1, "xg"

        def fake_prob(*_args, **_kwargs):
            return {"prob_casa": 0.62, "prob_empate": 0.20, "prob_fora": 0.18}

        def fake_ou(*_args, **_kwargs):
            return {"prob_over": 0.65, "prob_under": 0.35, "linha": 2.5}

        xg_understat.calcular_media_gols_com_xg = fake_xg
        poisson.calcular_probabilidades = fake_prob
        poisson.calcular_prob_over_under = fake_ou
        return old_xg, old_prob, old_ou

    def _restore_dependencies(self, old_xg, old_prob, old_ou):
        xg_understat.calcular_media_gols_com_xg = old_xg
        poisson.calcular_probabilidades = old_prob
        poisson.calcular_prob_over_under = old_ou

    def test_relatorio_inclui_markets_core_com_metricas(self):
        df = pd.DataFrame(
            [
                {"liga": "Premier League", "time_casa": "A", "time_fora": "B", "gols_casa": 2, "gols_fora": 1, "odd_over25": 1.9, "odd_pinn_casa": 2.0, "odd_pinn_fora": 8.0},
                {"liga": "Premier League", "time_casa": "C", "time_fora": "D", "gols_casa": 0, "gols_fora": 2, "odd_over25": 1.95, "odd_pinn_casa": 2.05, "odd_pinn_fora": 8.5},
                {"liga": "La Liga", "time_casa": "E", "time_fora": "F", "gols_casa": 1, "gols_fora": 1, "odd_over25": 1.88, "odd_pinn_casa": 2.1, "odd_pinn_fora": 8.2},
            ]
        )

        old_xg, old_prob, old_ou = self._patch_dependencies()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = calibrador.calcular_win_rate_historico(df)

            self.assertIn("1x2_casa", result)
            self.assertIn("1x2_fora", result)
            self.assertIn("win_rate_pct", result["1x2_casa"])
            self.assertIn("roi_pct", result["1x2_casa"])
            self.assertGreaterEqual(result["1x2_casa"]["total"], 1)
            self.assertIn("Qualidade", output.getvalue())
        finally:
            self._restore_dependencies(old_xg, old_prob, old_ou)

    def test_zero_state_explicito_quando_sem_sinais(self):
        df = pd.DataFrame(
            [
                {"liga": "Serie A", "time_casa": "G", "time_fora": "H", "gols_casa": 0, "gols_fora": 0, "odd_over25": 1.2, "odd_pinn_casa": 1.2, "odd_pinn_fora": 1.2},
                {"liga": "Serie A", "time_casa": "I", "time_fora": "J", "gols_casa": 1, "gols_fora": 0, "odd_over25": 1.25, "odd_pinn_casa": 1.25, "odd_pinn_fora": 1.25},
            ]
        )

        old_xg, old_prob, old_ou = self._patch_dependencies()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = calibrador.calcular_win_rate_historico(df)

            self.assertEqual(result["over_2.5"]["total"], 0)
            self.assertEqual(result["1x2_casa"]["total"], 0)
            self.assertEqual(result["1x2_fora"]["total"], 0)
            self.assertIn("sem_sinal", output.getvalue())
        finally:
            self._restore_dependencies(old_xg, old_prob, old_ou)

    def test_retorno_tem_campos_de_auditoria(self):
        df = pd.DataFrame(
            [
                {"liga": "Bundesliga", "time_casa": "K", "time_fora": "L", "gols_casa": 3, "gols_fora": 1, "odd_over25": 2.0, "odd_pinn_casa": 2.0, "odd_pinn_fora": 8.0},
            ]
        )

        old_xg, old_prob, old_ou = self._patch_dependencies()
        try:
            result = calibrador.calcular_win_rate_historico(df)
            market = result["1x2_casa"]
            self.assertIn("total", market)
            self.assertIn("wins", market)
            self.assertIn("lucro", market)
            self.assertIn("ev_soma", market)
            self.assertIn("qualidade", market)
            self.assertEqual(market["qualidade"], "baixa_amostra")
        finally:
            self._restore_dependencies(old_xg, old_prob, old_ou)


if __name__ == "__main__":
    unittest.main()
