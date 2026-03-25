import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import types

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

if "telegram" not in sys.modules:
    telegram_stub = types.ModuleType("telegram")

    class _BotStub:
        def __init__(self, *args, **kwargs):
            pass

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

    class _RequestException(Exception):
        pass

    requests_stub.RequestException = _RequestException
    requests_stub.exceptions = types.SimpleNamespace(RequestException=_RequestException)

    class _ResponseStub:
        status_code = 200

        def json(self):
            return []

    def _get_stub(*args, **kwargs):
        return _ResponseStub()

    requests_stub.get = _get_stub
    sys.modules["requests"] = requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")

    def _load_dotenv_stub(*args, **kwargs):
        return True

    dotenv_stub.load_dotenv = _load_dotenv_stub
    sys.modules["dotenv"] = dotenv_stub

import scheduler


class TestSchedulerDryRun(unittest.TestCase):
    def test_executar_dry_run_once_finaliza_com_sucesso(self):
        with patch("scheduler.processar_jogos", new=AsyncMock(return_value=None)) as mocked_processar:
            rc = scheduler.executar_dry_run_once()

        self.assertEqual(rc, 0)
        mocked_processar.assert_awaited_once_with(dry_run=True)

    def test_dry_run_nao_instancia_telegram_bot(self):
        with patch("scheduler.buscar_jogos_com_odds", return_value=[]), \
             patch("scheduler.formatar_jogos", return_value=[]), \
             patch("scheduler.Bot") as mocked_bot:
            asyncio.run(scheduler.processar_jogos(dry_run=True))

        mocked_bot.assert_not_called()

    def test_dry_run_emite_log_cycle_totals(self):
        with patch("scheduler.buscar_jogos_com_odds", return_value=[]), \
             patch("scheduler.formatar_jogos", return_value=[]), \
             patch("scheduler.log_event") as mocked_log:
            asyncio.run(scheduler.processar_jogos(dry_run=True))

        chamadas = [c.args for c in mocked_log.call_args_list]
        cycle_calls = [args for args in chamadas if args[0] == "scheduler" and args[1] == "cycle_totals"]
        self.assertTrue(cycle_calls)
        detalhes = cycle_calls[-1][5]
        self.assertIn("prior_context_counts", detalhes)


if __name__ == "__main__":
    unittest.main()
