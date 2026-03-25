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
            return float(sum(sum(row) for row in self))

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


class TestSchedulerGuardrails(unittest.TestCase):
    def test_aplicar_canary_operacional_limita_lote(self):
        base = [1, 2, 3, 4]
        liberados, suprimidos = scheduler.aplicar_canary_operacional(base, ratio=0.5, enabled=True)
        self.assertEqual(liberados, [1, 2])
        self.assertEqual(suprimidos, [3, 4])

    def test_aplicar_canary_operacional_sem_modo_retorna_tudo(self):
        base = [1, 2, 3]
        liberados, suprimidos = scheduler.aplicar_canary_operacional(base, ratio=0.2, enabled=False)
        self.assertEqual(liberados, base)
        self.assertEqual(suprimidos, [])

    def test_avaliar_guardrails_hard_limits_bloqueia_perda_diaria(self):
        with patch("scheduler.calcular_perda_diaria_unidades", return_value=-20.0), patch(
            "scheduler.calcular_exposicao_pendente_unidades", return_value=1.0
        ), patch.object(scheduler, "MAX_DAILY_LOSS_UNITS", 8.0):
            resultado = scheduler.avaliar_guardrails_hard_limits()

        self.assertTrue(resultado["bloquear"])
        self.assertEqual(resultado["codigo"], "hard_daily_loss_limit")

    def test_avaliar_guardrails_hard_limits_bloqueia_exposicao(self):
        with patch("scheduler.calcular_perda_diaria_unidades", return_value=-1.0), patch(
            "scheduler.calcular_exposicao_pendente_unidades", return_value=15.0
        ), patch.object(scheduler, "MAX_EXPOSURE_WINDOW_UNITS", 10.0):
            resultado = scheduler.avaliar_guardrails_hard_limits()

        self.assertTrue(resultado["bloquear"])
        self.assertEqual(resultado["codigo"], "hard_exposure_window_limit")

    def test_calcular_provider_error_rate(self):
        provider_health = {
            "ok": 4,
            "timeout": 2,
            "http_error": 1,
            "connection_error": 1,
            "empty_payload": 0,
            "unknown_error": 0,
        }
        self.assertAlmostEqual(scheduler.calcular_provider_error_rate(provider_health), 0.5)

    def test_avaliar_slo_alertas_dispara_fallback_e_disponibilidade(self):
        with patch(
            "scheduler.obter_slo_disponibilidade_ciclo",
            return_value={"total": 10, "saudaveis": 8, "disponibilidade": 0.8},
        ), patch.object(scheduler, "SLO_CYCLE_AVAILABILITY_MIN", 0.95), patch.object(
            scheduler, "SLO_FALLBACK_RATE_MAX", 0.2
        ):
            alertas = scheduler.avaliar_slo_alertas(
                provider_health={"fallback_used": 3},
                total_avaliacoes_mercado=10,
                ciclo_duracao_segundos=12.0,
                drift_alerta=None,
            )

        codigos = {a["codigo"] for a in alertas}
        self.assertIn("slo_cycle_availability_breach", codigos)
        self.assertIn("slo_fallback_rate_breach", codigos)


if __name__ == "__main__":
    unittest.main()
