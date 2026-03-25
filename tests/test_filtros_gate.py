import sys
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model"
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

import filtros
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

    def test_gate1_usa_no_vig_quando_odd_oponente_disponivel(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.80,
                "odd_oponente_mercado": 2.00,
                "no_vig_source_quality": "sharp",
                "mercado": "over_2.5",
                "prob_modelo": 0.73,
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertFalse(resultado["aprovado"])
        self.assertEqual(resultado["bloqueado_em"], "Gate 1")
        self.assertEqual(resultado["reason_code"], REJECT_REASON_CODES["gate1_ev"])

    def test_gate1_nao_aplica_no_vig_sem_fonte_sharp(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.80,
                "odd_oponente_mercado": 2.00,
                "no_vig_source_quality": "fallback",
                "mercado": "over_2.5",
                "prob_modelo": 0.73,
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertTrue(resultado["aprovado"])
        self.assertEqual(resultado["reason_code"], REJECT_CODE_PASSED)

    def test_gate1_usa_prob_modelo_base_pre_contexto(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.90,
                "odd_oponente_mercado": 1.95,
                "no_vig_source_quality": "sharp",
                "mercado": "over_2.5",
                "prob_modelo": 0.80,
                "prob_modelo_base": 0.55,
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertTrue(resultado["aprovado"])
        self.assertEqual(resultado["reason_code"], REJECT_CODE_PASSED)

    def test_gate1_fallback_legado_sem_odd_oponente(self):
        resultado = aplicar_triple_gate(
            {
                "ev": 0.08,
                "odd": 1.80,
                "mercado": "over_2.5",
                "prob_modelo": 0.73,
                "escalacao_confirmada": True,
                "variacao_odd": 0.0,
            },
            sinais_hoje=0,
        )

        self.assertTrue(resultado["aprovado"])
        self.assertEqual(resultado["reason_code"], REJECT_CODE_PASSED)


class TestStandingsCachePersistencia(unittest.TestCase):
    def setUp(self):
        filtros._cache_standings.clear()
        filtros._cache_ts.clear()
        filtros._cache_persistido_carregado = False

    def _fake_response(self, rank=1, points=70):
        class _Resp:
            status_code = 200

            def json(self_inner):
                return {
                    "response": [
                        {
                            "league": {
                                "standings": [
                                    [
                                        {
                                            "team": {"name": "Arsenal"},
                                            "rank": rank,
                                            "points": points,
                                            "all": {"played": 30},
                                        }
                                    ]
                                ]
                            }
                        }
                    ]
                }

        return _Resp()

    def test_cache_reaproveita_persistencia_entre_reloads(self):
        with tempfile.TemporaryDirectory() as td:
            cache_path = os.path.join(td, "standings_cache.json")
            with patch.object(filtros, "STANDINGS_CACHE_PATH", cache_path), patch.dict(os.environ, {"API_FOOTBALL_KEY": "token"}):
                with patch("requests.get", return_value=self._fake_response(rank=2, points=61)) as mocked_get:
                    dados_1 = filtros.buscar_standings(39, temporada=2026)
                    self.assertTrue(dados_1)
                    self.assertEqual(mocked_get.call_count, 1)

                filtros._cache_standings.clear()
                filtros._cache_ts.clear()
                filtros._cache_persistido_carregado = False

                with patch("requests.get") as mocked_get_reload:
                    dados_2 = filtros.buscar_standings(39, temporada=2026)
                    self.assertTrue(dados_2)
                    self.assertEqual(mocked_get_reload.call_count, 0)

    def test_cache_expirado_forca_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            cache_path = os.path.join(td, "standings_cache.json")
            key = "39_2026"
            payload = {
                key: {
                    "ts": "2000-01-01T00:00:00",
                    "standings": {"arsenal": {"posicao": 1, "pontos": 80, "jogos_restantes": 1, "total_times": 20}},
                }
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            with patch.object(filtros, "STANDINGS_CACHE_PATH", cache_path), patch.dict(os.environ, {"API_FOOTBALL_KEY": "token"}), patch("requests.get", return_value=self._fake_response(rank=4, points=55)) as mocked_get:
                dados = filtros.buscar_standings(39, temporada=2026)
                self.assertTrue(dados)
                self.assertEqual(mocked_get.call_count, 1)
                self.assertEqual(dados.get("arsenal", {}).get("posicao"), 4)


if __name__ == "__main__":
    unittest.main()
