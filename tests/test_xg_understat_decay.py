import json
import os
import tempfile
import unittest
from unittest.mock import patch
import sys
import types

from data import xg_understat


class TestXGUnderstatDecay(unittest.TestCase):
    def test_media_ponderada_temporal_prioriza_recencia(self):
        valores = [0.5, 0.8, 2.0]
        ponderada = xg_understat._media_ponderada_temporal(valores, decay_base=0.9)
        simples = round(sum(valores) / len(valores), 3)

        self.assertGreater(ponderada, simples)

    def test_media_ponderada_temporal_fallback_lista_vazia(self):
        self.assertEqual(xg_understat._media_ponderada_temporal([]), 1.2)

    def test_calcular_media_gols_com_xg_mantem_contrato(self):
        payload = {
            "Time Casa": {
                "xg_marcado_casa": 1.5,
                "xg_marcado_fora": 1.0,
                "xg_sofrido_casa": 0.9,
                "xg_sofrido_fora": 1.1,
            },
            "Time Fora": {
                "xg_marcado_casa": 1.2,
                "xg_marcado_fora": 1.3,
                "xg_sofrido_casa": 1.0,
                "xg_sofrido_fora": 1.4,
            },
        }

        with tempfile.TemporaryDirectory() as td:
            xg_path = os.path.join(td, "xg_dados.json")
            with open(xg_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            fake_stats = types.ModuleType("atualizar_stats")
            fake_stats.carregar_medias = lambda: {}
            sys.modules["atualizar_stats"] = fake_stats

            with patch.object(xg_understat, "XG_PATH", xg_path):
                media_casa, media_fora, fonte = xg_understat.calcular_media_gols_com_xg(
                    "Time Casa", "Time Fora"
                )

            del sys.modules["atualizar_stats"]

        self.assertIsInstance(media_casa, float)
        self.assertIsInstance(media_fora, float)
        self.assertEqual(fonte, "xG")


if __name__ == "__main__":
    unittest.main()
