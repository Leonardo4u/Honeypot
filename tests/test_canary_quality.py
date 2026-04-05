import sys
import types


if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

if "telegram" not in sys.modules:
    telegram_stub = types.ModuleType("telegram")

    class _BotStub:
        def __init__(self, *args, **kwargs):
            pass

    setattr(telegram_stub, "Bot", _BotStub)
    sys.modules["telegram"] = telegram_stub

if "scipy" not in sys.modules:
    scipy_stub = types.ModuleType("scipy")
    scipy_stats_stub = types.ModuleType("scipy.stats")
    scipy_optimize_stub = types.ModuleType("scipy.optimize")

    class _PoissonStub:
        @staticmethod
        def pmf(*args, **kwargs):
            return 0.0

    setattr(scipy_stats_stub, "poisson", _PoissonStub())

    def _minimize_stub(*args, **kwargs):
        class _Result:
            x = [0.0]
            success = True

        return _Result()

    setattr(scipy_optimize_stub, "minimize", _minimize_stub)
    setattr(scipy_stub, "stats", scipy_stats_stub)
    setattr(scipy_stub, "optimize", scipy_optimize_stub)
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

    setattr(numpy_stub, "zeros", _zeros)
    setattr(numpy_stub, "mean", _mean)
    sys.modules["numpy"] = numpy_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    setattr(requests_stub, "RequestException", _RequestException)
    setattr(requests_stub, "exceptions", types.SimpleNamespace(RequestException=_RequestException))

    class _ResponseStub:
        status_code = 200

        def json(self):
            return []

    def _get_stub(*args, **kwargs):
        return _ResponseStub()

    setattr(requests_stub, "get", _get_stub)
    sys.modules["requests"] = requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")

    def _load_dotenv_stub(*args, **kwargs):
        return True

    setattr(dotenv_stub, "load_dotenv", _load_dotenv_stub)
    sys.modules["dotenv"] = dotenv_stub

import scheduler


def test_canary_desativado_mantem_bloqueio_source_quality_low(monkeypatch):
    monkeypatch.delenv("EDGE_QUALITY_CANARY_ENABLED", raising=False)
    aprovado = scheduler._is_quality_canary_candidate(source_quality_low=True, edge=0.90, score=85)
    assert aprovado is False


def test_canary_ativado_aceita_pick_com_edge_alto(monkeypatch):
    monkeypatch.setenv("EDGE_QUALITY_CANARY_ENABLED", "1")
    aprovado = scheduler._is_quality_canary_candidate(source_quality_low=True, edge=0.90, score=85)
    assert aprovado is True


def test_canary_ativado_bloqueia_edge_baixo(monkeypatch):
    monkeypatch.setenv("EDGE_QUALITY_CANARY_ENABLED", "1")
    aprovado = scheduler._is_quality_canary_candidate(source_quality_low=True, edge=0.45, score=85)
    assert aprovado is False


def test_canary_ativado_bloqueia_score_baixo(monkeypatch):
    monkeypatch.setenv("EDGE_QUALITY_CANARY_ENABLED", "1")
    aprovado = scheduler._is_quality_canary_candidate(source_quality_low=True, edge=0.90, score=78)
    assert aprovado is False


def test_canary_stake_override_e_um_porcento(monkeypatch):
    monkeypatch.setenv("EDGE_QUALITY_CANARY_ENABLED", "1")
    kelly_payload = {"banca_atual": 1000.0, "kelly_final_pct": 5.0, "valor_reais": 50.0}
    stake_pct, stake_reais = scheduler._apply_quality_canary_stake_override(kelly_payload)
    assert stake_pct == 1.0
    assert stake_reais == 10.0


def test_canary_emite_log(monkeypatch, caplog):
    monkeypatch.setenv("EDGE_QUALITY_CANARY_ENABLED", "1")
    with caplog.at_level("INFO"):
        scheduler._emit_quality_canary_log(edge=0.90, score=85)
    assert "[CANARY]" in caplog.text
