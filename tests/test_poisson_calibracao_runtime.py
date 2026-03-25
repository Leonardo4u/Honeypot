import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import calibrar_modelo
import poisson


class TestPoissonCalibracaoRuntime(unittest.TestCase):
    def setUp(self):
        self.old_path_poisson = poisson.CALIBRACAO_LIGAS_PATH
        self.old_path_calibrador = calibrar_modelo.CALIBRACAO_LIGAS_PATH
        poisson._reset_calibracao_cache()

    def tearDown(self):
        poisson.CALIBRACAO_LIGAS_PATH = self.old_path_poisson
        calibrar_modelo.CALIBRACAO_LIGAS_PATH = self.old_path_calibrador
        poisson._reset_calibracao_cache()

    def test_prioriza_calibracao_arquivo_e_aplica_home_advantage(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "calibracao_ligas.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "ligas": {
                            "Premier League": {
                                "rho": -0.02,
                                "home_advantage": 1.2,
                                "amostra_jogos": 500,
                            }
                        }
                    },
                    f,
                )

            poisson.CALIBRACAO_LIGAS_PATH = path
            poisson._reset_calibracao_cache()

            resultado = poisson.calcular_probabilidades(1.4, 1.1, liga="Premier League")
            base_sem_adv = poisson.calcular_probabilidades(1.4, 1.1, liga="Premier League", rho=-0.02)

            self.assertEqual(resultado["rho_usado"], -0.02)
            self.assertAlmostEqual(resultado["home_advantage_usado"], 1.2, places=3)
            self.assertGreater(resultado["prob_casa"], base_sem_adv["prob_casa"])

    def test_fallback_sem_arquivo_usa_default(self):
        poisson.CALIBRACAO_LIGAS_PATH = os.path.join("nao", "existe", "calibracao_ligas.json")
        poisson._reset_calibracao_cache()

        resultado = poisson.calcular_probabilidades(1.3, 1.0, liga="Liga Inexistente")
        self.assertEqual(resultado["rho_usado"], poisson.RHO_DEFAULT)
        self.assertAlmostEqual(resultado["home_advantage_usado"], 1.0, places=3)

    def test_calibrador_salva_arquivo_runtime(self):
        df = pd.DataFrame(
            [
                {"liga": "Premier League", "gols_casa": 2, "gols_fora": 1},
                {"liga": "Premier League", "gols_casa": 1, "gols_fora": 0},
                {"liga": "La Liga", "gols_casa": 0, "gols_fora": 0},
                {"liga": "La Liga", "gols_casa": 2, "gols_fora": 2},
            ]
        )

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "calibracao_ligas.json")
            calibrar_modelo.CALIBRACAO_LIGAS_PATH = path

            with patch("poisson.estimar_rho", side_effect=[-0.03, -0.07]):
                rho_calibrado = calibrar_modelo.calibrar_rho_por_liga(df)

            self.assertEqual(rho_calibrado["La Liga"], -0.03)
            self.assertEqual(rho_calibrado["Premier League"], -0.07)
            self.assertTrue(os.path.exists(path))

            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            self.assertIn("atualizado_em", payload)
            self.assertIn("ligas", payload)
            self.assertIn("Premier League", payload["ligas"])
            self.assertIn("rho", payload["ligas"]["Premier League"])
            self.assertIn("home_advantage", payload["ligas"]["Premier League"])

    def test_falha_salvar_nao_quebra_calibracao(self):
        df = pd.DataFrame(
            [{"liga": "Premier League", "gols_casa": 2, "gols_fora": 1}]
        )

        with patch("poisson.estimar_rho", return_value=-0.04):
            with patch("calibrar_modelo.json.dump", side_effect=OSError("falha")):
                saida = calibrar_modelo.calibrar_rho_por_liga(df)

        self.assertIn("Premier League", saida)


if __name__ == "__main__":
    unittest.main()
