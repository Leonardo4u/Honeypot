import unittest
from unittest.mock import patch

from data import kelly_banca


class TestKellyBancaCorrelation(unittest.TestCase):
    @patch("data.kelly_banca.carregar_estado_banca", return_value={"banca_atual": 1000.0, "banca_inicial": 1000.0, "banca_maxima": 1000.0})
    @patch("data.kelly_banca.calcular_exposicao_atual", return_value=0.0)
    def test_sem_correlacao_mantem_baseline(self, _mock_exposicao, _mock_estado):
        baseline = kelly_banca.calcular_kelly(
            prob_modelo=0.55,
            odd=1.90,
            edge_score=85,
            sinais_abertos=0,
            sinais_liga_hoje=0,
            sinais_mesmo_jogo_abertos=0,
        )
        correlacionado = kelly_banca.calcular_kelly(
            prob_modelo=0.55,
            odd=1.90,
            edge_score=85,
            sinais_abertos=0,
            sinais_liga_hoje=0,
            sinais_mesmo_jogo_abertos=2,
        )

        self.assertTrue(baseline["aprovado"])
        self.assertTrue(correlacionado["aprovado"])
        self.assertGreater(baseline["kelly_final_pct"], correlacionado["kelly_final_pct"])

    @patch("data.kelly_banca.carregar_estado_banca", return_value={"banca_atual": 1000.0, "banca_inicial": 1000.0, "banca_maxima": 1000.0})
    @patch("data.kelly_banca.calcular_exposicao_atual", return_value=0.0)
    def test_payload_explicita_fator_correlacao(self, _mock_exposicao, _mock_estado):
        resultado = kelly_banca.calcular_kelly(
            prob_modelo=0.62,
            odd=1.95,
            edge_score=85,
            sinais_abertos=0,
            sinais_liga_hoje=0,
            sinais_mesmo_jogo_abertos=1,
        )

        self.assertTrue(resultado["aprovado"])
        self.assertIn("fator_correlacao_mesmo_jogo", resultado)
        self.assertLess(resultado["fator_correlacao_mesmo_jogo"], 1.0)

    @patch("data.kelly_banca.carregar_estado_banca", return_value={"banca_atual": 1000.0, "banca_inicial": 1000.0, "banca_maxima": 1000.0})
    @patch("data.kelly_banca.calcular_exposicao_atual", return_value=0.0)
    def test_reducao_correlacao_nao_gera_saida_invalida(self, _mock_exposicao, _mock_estado):
        resultado = kelly_banca.calcular_kelly(
            prob_modelo=0.60,
            odd=1.90,
            edge_score=90,
            sinais_abertos=3,
            sinais_liga_hoje=0,
            sinais_mesmo_jogo_abertos=5,
        )

        if resultado["aprovado"]:
            self.assertGreaterEqual(resultado["kelly_final_pct"], 0)
            self.assertGreaterEqual(resultado["valor_reais"], 0)
        else:
            self.assertIn("motivo", resultado)


if __name__ == "__main__":
    unittest.main()
