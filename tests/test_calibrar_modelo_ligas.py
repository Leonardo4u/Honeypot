import json
import os
import tempfile
import unittest

import pandas as pd

import calibrar_modelo


class TestCalibrarModeloLigas(unittest.TestCase):
    def test_build_ligas_calibration_writes_expected_schema(self):
        with tempfile.TemporaryDirectory() as td:
            old_path = calibrar_modelo.CALIBRACAO_LIGAS_PATH
            old_baixar = calibrar_modelo.baixar_dados_historicos
            old_carregar = calibrar_modelo.carregar_historico

            def _fake_baixar():
                return 120

            def _fake_carregar():
                rows = []
                for i in range(60):
                    rows.append({"liga": "Premier League", "gols_casa": 2, "gols_fora": 1})
                for i in range(30):
                    rows.append({"liga": "La Liga", "gols_casa": 1, "gols_fora": 1})
                return pd.DataFrame(rows)

            calibrar_modelo.CALIBRACAO_LIGAS_PATH = os.path.join(td, "calibracao_ligas.json")
            calibrar_modelo.baixar_dados_historicos = _fake_baixar
            calibrar_modelo.carregar_historico = _fake_carregar

            try:
                out = calibrar_modelo.build_ligas_calibration(min_matches=50, recency_halflife=38)
                self.assertIn("Premier League", out)
                self.assertNotIn("La Liga", out)
                self.assertEqual(out["Premier League"]["recency_halflife"], 38)

                with open(calibrar_modelo.CALIBRACAO_LIGAS_PATH, "r", encoding="utf-8-sig") as f:
                    payload = json.load(f)
                self.assertIn("Premier League", payload)
                self.assertIn("rho", payload["Premier League"])
                self.assertIn("home_advantage", payload["Premier League"])
            finally:
                calibrar_modelo.CALIBRACAO_LIGAS_PATH = old_path
                calibrar_modelo.baixar_dados_historicos = old_baixar
                calibrar_modelo.carregar_historico = old_carregar


if __name__ == "__main__":
    unittest.main()
