import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from model.analisar_jogo import analisar_jogo


class TestAnalisarJogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = ROOT / "tests" / "fixtures" / "jogo_base.json"
        with fixture_path.open("r", encoding="utf-8-sig") as f:
            cls.base = json.load(f)

    def test_descartar_quando_ev_insuficiente(self):
        entrada = copy.deepcopy(self.base)
        entrada["odd"] = 1.20

        resultado = analisar_jogo(entrada)

        self.assertEqual(resultado["decisao"], "DESCARTAR")
        self.assertIn("motivo", resultado)
        self.assertTrue(resultado["motivo"])

    def test_aprovado_retorna_campos_esperados(self):
        resultado = analisar_jogo(copy.deepcopy(self.base))

        self.assertIn(resultado["decisao"], {"PREMIUM", "PADRAO"})
        self.assertIn("edge_score", resultado)
        self.assertIn("stake_unidades", resultado)
        self.assertIn("rho_usado", resultado)
        self.assertGreaterEqual(resultado["edge_score"], 0)

    def test_mesma_entrada_produz_resultado_deterministico(self):
        r1 = analisar_jogo(copy.deepcopy(self.base))
        r2 = analisar_jogo(copy.deepcopy(self.base))

        self.assertEqual(r1["decisao"], r2["decisao"])
        self.assertEqual(r1["edge_score"], r2["edge_score"])
        self.assertEqual(r1["ev"], r2["ev"])


if __name__ == "__main__":
    unittest.main()
