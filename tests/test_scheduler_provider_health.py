import unittest
from unittest.mock import patch
import sys
import types
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: None
    requests_stub.Timeout = Exception
    requests_stub.ConnectionError = Exception
    sys.modules["requests"] = requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from data.coletar_odds import (
    atualizar_contadores_provider_health,
    buscar_jogos_com_odds,
    buscar_jogos_com_odds_com_status,
    formatar_jogos,
)


class TestProviderHealthCounters(unittest.TestCase):
    def setUp(self):
        self.provider_health = {
            "ok": 0,
            "timeout": 0,
            "http_error": 0,
            "connection_error": 0,
            "empty_payload": 0,
            "unknown_error": 0,
            "invalid_input": 0,
            "fallback_used": 0,
        }

    def test_ok_incrementa_somente_ok(self):
        categoria = atualizar_contadores_provider_health(self.provider_health, "ok")

        self.assertEqual(categoria, "ok")
        self.assertEqual(self.provider_health["ok"], 1)
        self.assertEqual(self.provider_health["timeout"], 0)
        self.assertEqual(self.provider_health["http_error"], 0)
        self.assertEqual(self.provider_health["connection_error"], 0)
        self.assertEqual(self.provider_health["empty_payload"], 0)
        self.assertEqual(self.provider_health["unknown_error"], 0)

    def test_timeout_http_connection_incrementam_categorias_corretas(self):
        atualizar_contadores_provider_health(self.provider_health, "timeout")
        atualizar_contadores_provider_health(self.provider_health, "http_error")
        atualizar_contadores_provider_health(self.provider_health, "connection_error")

        self.assertEqual(self.provider_health["timeout"], 1)
        self.assertEqual(self.provider_health["http_error"], 1)
        self.assertEqual(self.provider_health["connection_error"], 1)

    def test_empty_payload_nao_vira_connection_error(self):
        atualizar_contadores_provider_health(self.provider_health, "empty_payload")

        self.assertEqual(self.provider_health["empty_payload"], 1)
        self.assertEqual(self.provider_health["connection_error"], 0)

    def test_status_desconhecido_vai_para_unknown_error(self):
        categoria = atualizar_contadores_provider_health(self.provider_health, "rate_limited_custom")

        self.assertEqual(categoria, "unknown_error")
        self.assertEqual(self.provider_health["unknown_error"], 1)


class TestBuscarJogosComStatus(unittest.TestCase):
    @patch("data.coletar_odds.request_with_retry")
    @patch("data.coletar_odds.API_KEY", "token_teste")
    def test_busca_com_status_retorna_ok(self, mocked_retry):
        mocked_retry.return_value = {
            "ok": True,
            "status": "ok",
            "data": [{"id": "x"}],
            "status_code": 200,
            "attempts_used": 1,
            "error": None,
        }

        result = buscar_jogos_com_odds_com_status("soccer_epl")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], [{"id": "x"}])

    @patch("data.coletar_odds.request_with_retry")
    @patch("data.coletar_odds.API_KEY", "token_teste")
    def test_busca_com_status_retorna_erro_timeout(self, mocked_retry):
        mocked_retry.return_value = {
            "ok": False,
            "status": "timeout",
            "data": None,
            "status_code": None,
            "attempts_used": 3,
            "error": "timeout",
        }

        result = buscar_jogos_com_odds_com_status("soccer_epl")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["data"], [])

    @patch("data.coletar_odds.request_with_retry")
    @patch("data.coletar_odds.API_KEY", "token_teste")
    def test_api_legada_buscar_jogos_com_odds_permanece_compativel(self, mocked_retry):
        mocked_retry.return_value = {
            "ok": True,
            "status": "ok",
            "data": [{"id": "abc"}],
            "status_code": 200,
            "attempts_used": 1,
            "error": None,
        }

        dados = buscar_jogos_com_odds("soccer_epl")

        self.assertEqual(dados, [{"id": "abc"}])

    def test_formatar_jogos_expoe_source_quality_por_mercado(self):
        commence_time = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        dados_api = [
            {
                "id": "j1",
                "sport_title": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": commence_time,
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 1.9},
                                    {"name": "Chelsea", "price": 3.8},
                                ],
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": 1.95},
                                    {"name": "Under", "price": 1.9},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

        jogos = formatar_jogos(dados_api)

        self.assertEqual(len(jogos), 1)
        self.assertEqual(jogos[0]["source_quality"]["1x2_casa"], "sharp")
        self.assertEqual(jogos[0]["source_quality"]["under_2.5"], "sharp")


if __name__ == "__main__":
    unittest.main()
