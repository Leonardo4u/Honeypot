import unittest
from unittest.mock import patch

from data import sos_ajuste


class TestSOSAjusteCaps(unittest.TestCase):
    def test_faixa_conservadora_para_medias(self):
        fake_sos = {
            "media_liga_xg_concedido": 1.2,
            "media_liga_xg_gerado": 1.2,
            "xg_concedido_defesa_fora": 2.6,
            "xg_gerado_ataque_fora": 2.3,
            "xg_concedido_defesa_casa": 0.3,
            "xg_gerado_ataque_casa": 0.2,
        }

        with patch("data.sos_ajuste.calcular_sos", return_value=fake_sos):
            xg_c, xg_f, status, detalhes = sos_ajuste.ajustar_xg_por_sos(
                1.4, 1.1, "A", "B", "soccer_epl", source_quality="médias"
            )

        self.assertEqual(status, "sos_aplicado")
        self.assertEqual(detalhes["cap_min"], 0.85)
        self.assertEqual(detalhes["cap_max"], 1.15)
        self.assertLessEqual(detalhes["fator_casa"], 1.15)
        self.assertGreaterEqual(detalhes["fator_fora"], 0.85)
        self.assertIsInstance(xg_c, float)
        self.assertIsInstance(xg_f, float)

    def test_faixa_ampla_para_xg(self):
        fake_sos = {
            "media_liga_xg_concedido": 1.2,
            "media_liga_xg_gerado": 1.2,
            "xg_concedido_defesa_fora": 2.6,
            "xg_gerado_ataque_fora": 2.3,
            "xg_concedido_defesa_casa": 0.3,
            "xg_gerado_ataque_casa": 0.2,
        }

        with patch("data.sos_ajuste.calcular_sos", return_value=fake_sos):
            _xg_c, _xg_f, status, detalhes = sos_ajuste.ajustar_xg_por_sos(
                1.4, 1.1, "A", "B", "soccer_epl", source_quality="xG"
            )

        self.assertEqual(status, "sos_aplicado")
        self.assertEqual(detalhes["cap_min"], 0.7)
        self.assertEqual(detalhes["cap_max"], 1.5)


if __name__ == "__main__":
    unittest.main()
