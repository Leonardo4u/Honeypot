import unittest
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR = os.path.join(ROOT_DIR, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

import poisson


class TestPoissonOverUnderDC(unittest.TestCase):
    def test_over_under_normalizado(self):
        resultado = poisson.calcular_prob_over_under(1.2, 0.9, linha=2.5, max_gols=10, rho=-0.1)
        soma = resultado["prob_over"] + resultado["prob_under"]
        self.assertAlmostEqual(soma, 1.0, places=3)

    def test_over_under_reflete_correcao_dc(self):
        # Cenario de baixa pontuacao onde o ajuste em placares baixos deve aparecer.
        com_dc = poisson.calcular_prob_over_under(0.7, 0.6, linha=1.5, max_gols=8, rho=-0.3)
        sem_dc = poisson.calcular_prob_over_under(0.7, 0.6, linha=1.5, max_gols=8, rho=0.0)

        self.assertNotEqual(com_dc["prob_under"], sem_dc["prob_under"])
        self.assertEqual(com_dc["linha"], 1.5)

    def test_assinatura_legada_permanece_valida(self):
        resultado = poisson.calcular_prob_over_under(1.4, 1.1)
        self.assertIn("prob_over", resultado)
        self.assertIn("prob_under", resultado)
        self.assertIn("rho_usado", resultado)


if __name__ == "__main__":
    unittest.main()
