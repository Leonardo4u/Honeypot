import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path

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

from data.verificar_resultados import buscar_resultado_jogo


class TestSettlementFixtureResolution(unittest.TestCase):
    @patch("data.verificar_resultados.request_with_retry")
    def test_resolver_prioriza_fixture_id_quando_disponivel(self, mocked_retry):
        mocked_retry.return_value = {
            "ok": True,
            "data": {
                "response": [
                    {
                        "fixture": {
                            "id": 9001,
                            "date": "2026-03-20T18:00:00+00:00",
                            "status": {"short": "FT"},
                        },
                        "teams": {
                            "home": {"name": "Arsenal"},
                            "away": {"name": "Chelsea"},
                        },
                        "goals": {"home": 2, "away": 1},
                    }
                ]
            },
        }

        resultado = buscar_resultado_jogo(
            time_casa="Arsenal",
            time_fora="Chelsea",
            fixture_id="9001",
            horario="2026-03-20T17:30:00Z",
        )

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["match_strategy"], "fixture_id")
        self.assertEqual(resultado["status"], "finalizado")
        self.assertEqual(resultado["fixture_id_api"], "9001")
        self.assertEqual(resultado["placar"], "2-1")
        called_params = mocked_retry.call_args.kwargs["params"]
        self.assertEqual(str(called_params.get("id")), "9001")

    @patch("data.verificar_resultados.request_with_retry")
    def test_resolver_usa_janela_data_e_escolhe_candidato_deterministico(self, mocked_retry):
        def fake_retry(**kwargs):
            params = kwargs.get("params", {})
            if params.get("date") == "2026-03-20":
                return {
                    "ok": True,
                    "data": {
                        "response": [
                            {
                                "fixture": {
                                    "id": 111,
                                    "date": "2026-03-20T09:00:00+00:00",
                                    "status": {"short": "FT"},
                                },
                                "teams": {
                                    "home": {"name": "Arsenal"},
                                    "away": {"name": "Chelsea"},
                                },
                                "goals": {"home": 0, "away": 0},
                            }
                        ]
                    },
                }
            if params.get("date") == "2026-03-21":
                return {
                    "ok": True,
                    "data": {
                        "response": [
                            {
                                "fixture": {
                                    "id": 222,
                                    "date": "2026-03-21T17:30:00+00:00",
                                    "status": {"short": "FT"},
                                },
                                "teams": {
                                    "home": {"name": "Arsenal"},
                                    "away": {"name": "Chelsea"},
                                },
                                "goals": {"home": 1, "away": 0},
                            }
                        ]
                    },
                }
            return {"ok": True, "data": {"response": []}}

        mocked_retry.side_effect = fake_retry

        resultado = buscar_resultado_jogo(
            time_casa="Arsenal",
            time_fora="Chelsea",
            horario="2026-03-21T17:30:00Z",
        )

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["match_strategy"], "date_window")
        self.assertEqual(resultado["fixture_id_api"], "222")
        self.assertEqual(resultado["placar"], "1-0")

    @patch("data.verificar_resultados.request_with_retry")
    def test_resolver_retorna_none_quando_nao_acha_candidato(self, mocked_retry):
        mocked_retry.return_value = {"ok": True, "data": {"response": []}}

        resultado = buscar_resultado_jogo(
            time_casa="Arsenal",
            time_fora="Chelsea",
            horario="2026-03-21T17:30:00Z",
        )

        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
