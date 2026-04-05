import importlib
import sys
import types
import unittest
from unittest.mock import patch

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

from data import verificar_resultados as _verificar_resultados


class TestSettlementFixtureResolution(unittest.TestCase):
    def setUp(self):
        # Isolamento defensivo: garante modulo limpo mesmo apos testes que mexem em sys.modules.
        self._vr = importlib.reload(_verificar_resultados)

    def test_obter_janela_settlement_por_competicao(self):
        self.assertEqual(self._vr.obter_janela_settlement_dias("UEFA Champions League"), 4)
        self.assertEqual(self._vr.obter_janela_settlement_dias("soccer_uefa_europa_league"), 4)
        self.assertEqual(self._vr.obter_janela_settlement_dias("Premier League"), 2)

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

        resultado = self._vr.buscar_resultado_jogo(
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

        resultado = self._vr.buscar_resultado_jogo(
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

        resultado = self._vr.buscar_resultado_jogo(
            time_casa="Arsenal",
            time_fora="Chelsea",
            horario="2026-03-21T17:30:00Z",
        )

        self.assertIsNone(resultado)

    @patch("data.verificar_resultados.request_with_retry")
    def test_janela_maior_para_competicao_aumenta_busca_por_datas(self, mocked_retry):
        mocked_retry.return_value = {"ok": True, "data": {"response": []}}

        resultado = self._vr.buscar_resultado_jogo(
            time_casa="Arsenal",
            time_fora="Chelsea",
            horario="2026-03-21T17:30:00Z",
            liga="UEFA Champions League",
        )

        self.assertIsNone(resultado)

        date_calls = [
            call
            for call in mocked_retry.call_args_list
            if call.kwargs.get("params", {}).get("date")
        ]
        self.assertEqual(len(date_calls), 9)


if __name__ == "__main__":
    unittest.main()
