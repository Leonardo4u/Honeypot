import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model"
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from filtros import aplicar_triple_gate
from signal_policy import (
    REJECT_CODE_LINEUP_UNCONFIRMED,
    REJECT_CODE_PASSED,
    REJECT_REASON_CODES,
)


class TestFiltrosGate(unittest.TestCase):
    def test_gate1_bloqueia_ev_baixo_com_reason_code_estavel(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.01,
                "odd": 1.90,
                "mercado": "over_2.5",
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertFalse(resultado["aprovado"])
        self.assertEqual(resultado["bloqueado_em"], "Gate 1")
        self.assertEqual(resultado["reason_code"], REJECT_REASON_CODES["gate1_ev"])
        self.assertIn("detalhes", resultado)

    def test_gate2_bloqueia_sem_escalacao_confirmada(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.90,
                "mercado": "over_2.5",
                "escalacao_confirmada": False,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertFalse(resultado["aprovado"])
        self.assertEqual(resultado["bloqueado_em"], "Gate 2")
        self.assertEqual(resultado["reason_code"], REJECT_CODE_LINEUP_UNCONFIRMED)

    def test_fluxo_aprovado_retorna_reason_code_passed(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.90,
                "mercado": "over_2.5",
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertTrue(resultado["aprovado"])
        self.assertIsNone(resultado["bloqueado_em"])
        self.assertEqual(resultado["reason_code"], REJECT_CODE_PASSED)
        self.assertIn("detalhes", resultado)


if __name__ == "__main__":
    unittest.main()
