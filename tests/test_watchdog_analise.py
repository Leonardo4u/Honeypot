import asyncio
import logging
import sys
import time
import types
from unittest.mock import patch


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


def _jogo_base():
    return {
        "jogo": "Casa FC vs Fora FC",
        "home_team": "Casa FC",
        "away_team": "Fora FC",
        "liga": "Liga Teste",
        "horario": "2026-04-05T15:15:00Z",
        "odds": {"casa": 2.0, "fora": 3.1, "over_2.5": 2.2, "under_2.5": 1.7},
        "source_quality": {"1x2_casa": "fallback"},
    }


def test_watchdog_pula_jogo_que_trava(caplog):
    def _analisar_lento(*args, **kwargs):
        time.sleep(1.2)
        return {"ok": True}

    alertas = []
    jogo = _jogo_base()
    dados = {"jogo": jogo["jogo"], "mercado": "1x2_casa"}

    with caplog.at_level(logging.ERROR):
        result = scheduler.analisar_jogo_com_timeout(
            dados,
            jogo=jogo,
            mercado="1x2_casa",
            timeout=1,
            analisar_fn=_analisar_lento,
            registrar_alerta_fn=lambda **kwargs: alertas.append(kwargs),
        )

    assert result is None
    assert "[WATCHDOG] Timeout de 1s" in caplog.text
    assert alertas


def test_watchdog_nao_interfere_em_jogo_normal(caplog):
    def _analisar_rapido(*args, **kwargs):
        return {"prediction_id": "ok"}

    jogo = _jogo_base()
    dados = {"jogo": jogo["jogo"], "mercado": "1x2_casa"}

    with caplog.at_level(logging.ERROR):
        result = scheduler.analisar_jogo_com_timeout(
            dados,
            jogo=jogo,
            mercado="1x2_casa",
            timeout=2,
            analisar_fn=_analisar_rapido,
            registrar_alerta_fn=lambda **kwargs: None,
        )

    assert result == {"prediction_id": "ok"}
    assert "[WATCHDOG] Timeout" not in caplog.text


def test_watchdog_timeout_configuravel(monkeypatch):
    monkeypatch.setenv("ANALISE_JOGO_TIMEOUT", "5")
    assert scheduler._timeout_analise_jogo_segundos() == 5


def test_watchdog_registra_telemetria(monkeypatch):
    def _analisar_lento(*args, **kwargs):
        time.sleep(1.2)
        return {"ok": True}

    alertas = []
    jogo = _jogo_base()
    dados = {"jogo": jogo["jogo"], "mercado": "1x2_casa"}

    scheduler.analisar_jogo_com_timeout(
        dados,
        jogo=jogo,
        mercado="1x2_casa",
        timeout=1,
        analisar_fn=_analisar_lento,
        registrar_alerta_fn=lambda **kwargs: alertas.append(kwargs),
    )

    assert len(alertas) == 1
    payload = alertas[0]
    assert payload["codigo"] == "watchdog_timeout"
    assert payload["detalhes"]["evento"] == "watchdog_timeout"
    assert payload["detalhes"]["timeout_segundos"] == 1


def test_watchdog_ciclo_encerra_graciosamente(monkeypatch, caplog):
    jogos = []
    for idx in range(10):
        jogo = _jogo_base().copy()
        jogo["jogo"] = f"Casa {idx} vs Fora {idx}"
        jogo["home_team"] = f"Casa {idx}"
        jogo["away_team"] = f"Fora {idx}"
        jogos.append(jogo)

    chamadas_analise = []

    def _analise_timeout_stub(*args, **kwargs):
        chamadas_analise.append(kwargs.get("jogo", {}).get("jogo"))
        return {
            "decisao": "PREMIUM",
            "ev": 0.1,
            "edge_score": 80,
            "prob_modelo": 0.6,
            "prediction_id": "stub",
        }

    monotonic_seq = iter([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

    def _fake_monotonic():
        try:
            return next(monotonic_seq)
        except StopIteration:
            return 99

    alertas = []

    monkeypatch.setattr(scheduler, "_garantir_schema_db", lambda: True)
    monkeypatch.setattr(scheduler, "buscar_sinais_hoje", lambda: [])
    monkeypatch.setattr(scheduler, "LIGAS", ["liga_teste"])
    monkeypatch.setattr(
        scheduler,
        "buscar_jogos_com_odds_com_status",
        lambda liga_key: {"status": "ok", "data": jogos},
    )
    monkeypatch.setattr(scheduler, "formatar_jogos", lambda data: data)
    monkeypatch.setattr(scheduler, "obter_media_gols", lambda *args, **kwargs: (1.2, 1.1, "xG"))
    monkeypatch.setattr(scheduler, "calcular_ajuste_forma", lambda *args, **kwargs: (0.0, 0.0))
    monkeypatch.setattr(
        scheduler,
        "listar_mercados_runtime",
        lambda: [{"mercado": "1x2_casa", "odd_key": "casa", "odd_oponente_key": "fora"}],
    )
    monkeypatch.setattr(scheduler, "calcular_confianca_contexto", lambda *args, **kwargs: {"confianca": 70, "qualidade_prior": "ok", "prior_ranking": 0.0, "amostra_prior": 10})
    monkeypatch.setattr(scheduler, "validar_entrada_analise", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(scheduler, "analisar_jogo_com_timeout", _analise_timeout_stub)
    monkeypatch.setattr(scheduler.DISPATCH_SERVICE, "should_dispatch", lambda analise: False)
    monkeypatch.setattr(scheduler, "registrar_alerta_operacional", lambda **kwargs: alertas.append(kwargs))
    monkeypatch.setattr(scheduler, "_timeout_ciclo_segundos", lambda: 5)
    monkeypatch.setattr(scheduler.time, "monotonic", _fake_monotonic)

    with patch("scheduler.Bot"):
        with caplog.at_level(logging.ERROR):
            asyncio.run(scheduler.processar_jogos(dry_run=False))

    assert len(chamadas_analise) < len(jogos)
    assert any(a.get("codigo") == "watchdog_cycle_timeout" for a in alertas)
    assert "[WATCHDOG] Ciclo ultrapassou 5s" in caplog.text
