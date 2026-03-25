import asyncio
import sys
import types
import unittest
from unittest.mock import patch


if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

if "telegram" not in sys.modules:
    telegram_stub = types.ModuleType("telegram")

    class _BotStub:
        def __init__(self, *args, **kwargs):
            pass

        async def set_message_reaction(self, *args, **kwargs):
            return None

    telegram_stub.Bot = _BotStub
    sys.modules["telegram"] = telegram_stub

if "scipy" not in sys.modules:
    scipy_stub = types.ModuleType("scipy")
    scipy_stats_stub = types.ModuleType("scipy.stats")
    scipy_optimize_stub = types.ModuleType("scipy.optimize")

    class _PoissonStub:
        @staticmethod
        def pmf(*args, **kwargs):
            return 0.0

    scipy_stats_stub.poisson = _PoissonStub()

    def _minimize_stub(*args, **kwargs):
        class _Result:
            x = [0.0]
            success = True

        return _Result()

    scipy_optimize_stub.minimize = _minimize_stub
    scipy_stub.stats = scipy_stats_stub
    scipy_stub.optimize = scipy_optimize_stub
    sys.modules["scipy"] = scipy_stub
    sys.modules["scipy.stats"] = scipy_stats_stub
    sys.modules["scipy.optimize"] = scipy_optimize_stub

if "numpy" not in sys.modules:
    numpy_stub = types.ModuleType("numpy")

    class _MatrixStub(list):
        def sum(self):
            total = 0.0
            for row in self:
                if isinstance(row, list):
                    total += sum(row)
                else:
                    total += float(row)
            return total

        def __truediv__(self, divisor):
            if divisor == 0:
                return self
            return _MatrixStub([[value / divisor for value in row] for row in self])

    def _zeros(shape):
        rows, cols = shape
        return _MatrixStub([[0.0 for _ in range(cols)] for _ in range(rows)])

    def _mean(values):
        if not values:
            return 0.0
        return sum(values) / len(values)

    numpy_stub.zeros = _zeros
    numpy_stub.mean = _mean
    sys.modules["numpy"] = numpy_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: None
    requests_stub.Timeout = Exception
    requests_stub.ConnectionError = Exception
    sys.modules["requests"] = requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: True
    sys.modules["dotenv"] = dotenv_stub

import scheduler


class _CursorStub:
    def __init__(self, pending_rows=None, message_ids=(None, None)):
        self.pending_rows = pending_rows or []
        self.message_ids = message_ids
        self.last_query = ""

    def execute(self, query, params=None):
        self.last_query = " ".join(query.split()).lower()

    def fetchall(self):
        if "where status = 'pendente'" in self.last_query:
            return self.pending_rows
        return []

    def fetchone(self):
        if "select message_id_vip, message_id_free" in self.last_query:
            return self.message_ids
        return None


class _ConnectionStub:
    def __init__(self, pending_rows=None, message_ids=(None, None)):
        self._cursor = _CursorStub(pending_rows=pending_rows, message_ids=message_ids)

    def cursor(self):
        return self._cursor

    def close(self):
        return None


class TestSchedulerSettlementIntegrity(unittest.TestCase):
    def test_pending_cross_day_persiste_fixture_sem_finalizar(self):
        pending = [
            (
                10,
                "Arsenal vs Chelsea",
                "1x2_casa",
                1.92,
                "2026-03-20T17:30:00Z",
                None,
                None,
                "UEFA Champions League",
            )
        ]

        fake_verificar = types.ModuleType("verificar_resultados")
        calls = []

        def _buscar_resultado_jogo(*args, **kwargs):
            calls.append(kwargs)
            return {
                "status": "nao_iniciado",
                "fixture_id_api": "555",
                "fixture_data_api": "2026-03-20",
                "match_strategy": "date_window",
            }

        fake_verificar.buscar_resultado_jogo = _buscar_resultado_jogo
        fake_verificar.avaliar_mercado = lambda *args, **kwargs: None

        fake_db = types.ModuleType("database")
        fixture_updates = []
        resultado_updates = []

        def _atualizar_fixture_referencia(sinal_id, fixture_id_api=None, fixture_data_api=None):
            fixture_updates.append((sinal_id, fixture_id_api, fixture_data_api))

        def _atualizar_resultado(sinal_id, resultado, lucro):
            resultado_updates.append((sinal_id, resultado, lucro))

        fake_db.atualizar_fixture_referencia = _atualizar_fixture_referencia
        fake_db.atualizar_resultado = _atualizar_resultado

        fake_exportar_excel = types.ModuleType("exportar_excel")
        fake_exportar_excel.gerar_excel = lambda *args, **kwargs: None

        first_conn = _ConnectionStub(pending_rows=pending)

        with patch.dict(
            sys.modules,
            {
                "verificar_resultados": fake_verificar,
                "database": fake_db,
                "exportar_excel": fake_exportar_excel,
            },
            clear=False,
        ):
            with patch("scheduler.sqlite3.connect", side_effect=[first_conn]), patch(
                "scheduler.atualizar_banca", return_value={"banca_atual": 100.0}
            ), patch("scheduler.atualizar_brier", return_value=0.2):
                asyncio.run(scheduler.verificar_resultados_automatico())

        self.assertEqual(calls[0]["horario"], "2026-03-20T17:30:00Z")
        self.assertIsNone(calls[0]["fixture_id"])
        self.assertEqual(calls[0]["liga"], "UEFA Champions League")
        self.assertEqual(fixture_updates, [(10, "555", "2026-03-20")])
        self.assertEqual(resultado_updates, [])

    def test_pending_com_fixture_id_reusa_identidade_e_finaliza(self):
        pending = [
            (
                11,
                "Arsenal vs Chelsea",
                "1x2_casa",
                1.92,
                "2026-03-20T17:30:00Z",
                "777",
                "2026-03-20",
                "Premier League",
            )
        ]

        fake_verificar = types.ModuleType("verificar_resultados")
        calls = []

        def _buscar_resultado_jogo(*args, **kwargs):
            calls.append(kwargs)
            return {
                "status": "finalizado",
                "gols_casa": 2,
                "gols_fora": 1,
                "placar": "2-1",
                "fixture_id_api": "777",
                "fixture_data_api": "2026-03-20",
                "match_strategy": "fixture_id",
            }

        def _avaliar_mercado(resultado, mercado, odd):
            return {"resultado": "verde", "lucro": round(odd - 1, 4)}

        fake_verificar.buscar_resultado_jogo = _buscar_resultado_jogo
        fake_verificar.avaliar_mercado = _avaliar_mercado

        fake_db = types.ModuleType("database")
        fixture_updates = []
        resultado_updates = []

        def _atualizar_fixture_referencia(sinal_id, fixture_id_api=None, fixture_data_api=None):
            fixture_updates.append((sinal_id, fixture_id_api, fixture_data_api))

        def _atualizar_resultado(sinal_id, resultado, lucro):
            resultado_updates.append((sinal_id, resultado, lucro))

        fake_db.atualizar_fixture_referencia = _atualizar_fixture_referencia
        fake_db.atualizar_resultado = _atualizar_resultado

        fake_exportar_excel = types.ModuleType("exportar_excel")
        fake_exportar_excel.gerar_excel = lambda *args, **kwargs: None

        first_conn = _ConnectionStub(pending_rows=pending)
        second_conn = _ConnectionStub(pending_rows=[], message_ids=(None, None))

        with patch.dict(
            sys.modules,
            {
                "verificar_resultados": fake_verificar,
                "database": fake_db,
                "exportar_excel": fake_exportar_excel,
            },
            clear=False,
        ):
            with patch("scheduler.sqlite3.connect", side_effect=[first_conn, second_conn]), patch(
                "scheduler.atualizar_banca", return_value={"banca_atual": 150.0}
            ), patch("scheduler.atualizar_brier", return_value=0.12), patch(
                "scheduler.atualizar_excel", return_value=None
            ):
                asyncio.run(scheduler.verificar_resultados_automatico())

        self.assertEqual(calls[0]["fixture_id"], "777")
        self.assertEqual(calls[0]["data"], "2026-03-20")
        self.assertEqual(calls[0]["liga"], "Premier League")
        self.assertEqual(fixture_updates, [(11, "777", "2026-03-20")])
        self.assertEqual(resultado_updates[0][0], 11)
        self.assertEqual(resultado_updates[0][1], "verde")


if __name__ == "__main__":
    unittest.main()
