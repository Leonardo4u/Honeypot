import asyncio
import sys
import types
import unittest
from contextlib import ExitStack
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


class _CursorStub:
    def execute(self, *args, **kwargs):
        return None

    def fetchall(self):
        return []


class _ConnStub:
    def cursor(self):
        return _CursorStub()

    def close(self):
        return None


class TestSchedulerQualityPriorRanking(unittest.TestCase):
    def _run_cycle(self, jogos, prior_contexto_por_jogo_mercado, gate_payload, mocked_log_event=None, gate_side_effect=None):
        def _fake_analisar(dados_analise, log_dc=False):
            return {
                "decisao": "APOSTAR",
                "edge_score": 80,
                "ev": 0.1,
                "prob_modelo": 0.62,
                "odd": dados_analise["odd"],
                "liga": dados_analise["liga"],
                "jogo": dados_analise["jogo"],
                "mercado": dados_analise["mercado"],
            }

        def _fake_confianca(home, away, liga=None, mercado=None):
            chave = (f"{home} vs {away}", mercado)
            return prior_contexto_por_jogo_mercado[chave]

        gate_patch = patch("scheduler.aplicar_triple_gate", return_value=gate_payload)
        if gate_side_effect is not None:
            gate_patch = patch("scheduler.aplicar_triple_gate", side_effect=gate_side_effect)

        patches = [
            patch.object(scheduler, "LIGAS", ["soccer_epl"]),
            patch("scheduler.sqlite3.connect", return_value=_ConnStub()),
            patch("scheduler.buscar_sinais_hoje", return_value=[]),
            patch("scheduler.buscar_jogos_com_odds_com_status", return_value={"status": "ok", "data": []}),
            patch("scheduler.formatar_jogos", return_value=jogos),
            patch("scheduler.obter_media_gols", return_value=(1.4, 1.2, "xG+SOS")),
            patch("scheduler.calcular_ajuste_forma", return_value=(0.0, 0.0)),
            patch("scheduler.calcular_confianca_contexto", side_effect=_fake_confianca),
            patch("scheduler.analisar_jogo", side_effect=_fake_analisar),
            patch("scheduler.buscar_odds_todas_casas", return_value=None),
            gate_patch,
            patch("scheduler.contar_sinais_abertos", return_value=0),
            patch("scheduler.contar_sinais_liga_hoje", return_value=0),
            patch(
                "scheduler.calcular_kelly",
                return_value={"aprovado": True, "tier": "padrao", "kelly_final_pct": 1.0, "valor_reais": 10.0},
            ),
            patch("scheduler.formatar_sinal_kelly", return_value="sinal"),
        ]
        if mocked_log_event is not None:
            patches.append(patch("scheduler.log_event", mocked_log_event))

        with patch("builtins.print") as mocked_print:
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                asyncio.run(scheduler.processar_jogos(dry_run=True))

        return mocked_print

    def test_prior_forte_desempata_ranking_com_edge_equivalente(self):
        jogos = [
            {
                "home_team": "TeamStrong",
                "away_team": "TeamA",
                "jogo": "TeamStrong vs TeamA",
                "liga": "Premier League",
                "horario": "2026-03-25T20:00:00Z",
                "odds": {"casa": 1.9, "fora": 3.2, "over_2.5": 1.9, "under_2.5": 1.95},
            },
            {
                "home_team": "TeamWeak",
                "away_team": "TeamB",
                "jogo": "TeamWeak vs TeamB",
                "liga": "Premier League",
                "horario": "2026-03-25T21:00:00Z",
                "odds": {"casa": 1.9, "fora": 3.2, "over_2.5": 1.9, "under_2.5": 1.95},
            },
        ]
        prior = {
            ("TeamStrong vs TeamA", "1x2_casa"): {
                "confianca": 70,
                "qualidade_prior": "ok",
                "amostra_prior": 50,
                "prior_ranking": 6.0,
            },
            ("TeamStrong vs TeamA", "1x2_fora"): {
                "confianca": 70,
                "qualidade_prior": "ok",
                "amostra_prior": 50,
                "prior_ranking": 5.5,
            },
            ("TeamStrong vs TeamA", "over_2.5"): {
                "confianca": 70,
                "qualidade_prior": "ok",
                "amostra_prior": 50,
                "prior_ranking": 6.0,
            },
            ("TeamStrong vs TeamA", "under_2.5"): {
                "confianca": 70,
                "qualidade_prior": "ok",
                "amostra_prior": 50,
                "prior_ranking": 5.0,
            },
            ("TeamWeak vs TeamB", "1x2_casa"): {
                "confianca": 70,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 8,
                "prior_ranking": -4.0,
            },
            ("TeamWeak vs TeamB", "1x2_fora"): {
                "confianca": 70,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 8,
                "prior_ranking": -4.5,
            },
            ("TeamWeak vs TeamB", "over_2.5"): {
                "confianca": 70,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 8,
                "prior_ranking": -4.0,
            },
            ("TeamWeak vs TeamB", "under_2.5"): {
                "confianca": 70,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 8,
                "prior_ranking": -4.2,
            },
        }

        mocked_print = self._run_cycle(
            jogos,
            prior,
            {"aprovado": True, "penalizacao_score": 0},
        )

        dry_run_msgs = [str(args[0]) for args, _ in mocked_print.call_args_list if args and "[dry-run] Simulado sinal:" in str(args[0])]
        self.assertGreaterEqual(len(dry_run_msgs), 2)
        self.assertIn("TeamStrong vs TeamA", dry_run_msgs[0])

    def test_expansao_mercados_envia_odd_oponente_para_gate(self):
        jogos = [
            {
                "home_team": "TeamGate",
                "away_team": "TeamE",
                "jogo": "TeamGate vs TeamE",
                "liga": "Premier League",
                "horario": "2026-03-25T20:00:00Z",
                "odds": {"casa": 1.9, "fora": 3.1, "over_2.5": 1.92, "under_2.5": 1.96},
            }
        ]

        prior = {
            ("TeamGate vs TeamE", "1x2_casa"): {"confianca": 72, "qualidade_prior": "ok", "amostra_prior": 20, "prior_ranking": 2.0},
            ("TeamGate vs TeamE", "1x2_fora"): {"confianca": 72, "qualidade_prior": "ok", "amostra_prior": 20, "prior_ranking": 1.5},
            ("TeamGate vs TeamE", "over_2.5"): {"confianca": 72, "qualidade_prior": "ok", "amostra_prior": 20, "prior_ranking": 1.0},
            ("TeamGate vs TeamE", "under_2.5"): {"confianca": 72, "qualidade_prior": "ok", "amostra_prior": 20, "prior_ranking": 0.5},
        }

        captured_payloads = []

        def _capture_gate(payload, sinais_hoje=0):
            captured_payloads.append(payload)
            return {"aprovado": True, "penalizacao_score": 0}

        self._run_cycle(jogos, prior, {"aprovado": True, "penalizacao_score": 0}, gate_side_effect=_capture_gate)

        self.assertTrue(captured_payloads)
        mercados = {p.get("mercado") for p in captured_payloads}
        self.assertIn("1x2_fora", mercados)
        self.assertIn("under_2.5", mercados)
        self.assertTrue(any(p.get("odd_oponente_mercado", 0) > 0 for p in captured_payloads))

    def test_prior_fraco_apenas_penaliza_sem_bloqueio_forcado(self):
        jogos = [
            {
                "home_team": "TeamNoSignal",
                "away_team": "TeamC",
                "jogo": "TeamNoSignal vs TeamC",
                "liga": "Premier League",
                "horario": "2026-03-25T22:00:00Z",
                "odds": {"casa": 1.95, "fora": 3.05, "over_2.5": 1.95, "under_2.5": 1.91},
            }
        ]
        prior = {
            ("TeamNoSignal vs TeamC", "1x2_casa"): {
                "confianca": 70,
                "qualidade_prior": "sem_sinal",
                "amostra_prior": 0,
                "prior_ranking": -5.0,
            },
            ("TeamNoSignal vs TeamC", "1x2_fora"): {
                "confianca": 70,
                "qualidade_prior": "sem_sinal",
                "amostra_prior": 0,
                "prior_ranking": -5.0,
            },
            ("TeamNoSignal vs TeamC", "over_2.5"): {
                "confianca": 70,
                "qualidade_prior": "sem_sinal",
                "amostra_prior": 0,
                "prior_ranking": -5.0,
            },
            ("TeamNoSignal vs TeamC", "under_2.5"): {
                "confianca": 70,
                "qualidade_prior": "sem_sinal",
                "amostra_prior": 0,
                "prior_ranking": -5.0,
            },
        }

        mocked_print = self._run_cycle(
            jogos,
            prior,
            {"aprovado": True, "penalizacao_score": 0},
        )

        dry_run_msgs = [str(args[0]) for args, _ in mocked_print.call_args_list if args and "[dry-run] Simulado sinal:" in str(args[0])]
        self.assertTrue(any("TeamNoSignal vs TeamC" in msg for msg in dry_run_msgs))

    def test_log_rejeicao_explica_contexto_prior(self):
        jogos = [
            {
                "home_team": "TeamReject",
                "away_team": "TeamD",
                "jogo": "TeamReject vs TeamD",
                "liga": "Premier League",
                "horario": "2026-03-25T23:00:00Z",
                "odds": {"casa": 1.88, "fora": 3.0, "over_2.5": 1.88, "under_2.5": 1.93},
            }
        ]
        prior = {
            ("TeamReject vs TeamD", "1x2_casa"): {
                "confianca": 71,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 6,
                "prior_ranking": -3.0,
            },
            ("TeamReject vs TeamD", "1x2_fora"): {
                "confianca": 71,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 6,
                "prior_ranking": -3.0,
            },
            ("TeamReject vs TeamD", "over_2.5"): {
                "confianca": 71,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 6,
                "prior_ranking": -3.0,
            },
            ("TeamReject vs TeamD", "under_2.5"): {
                "confianca": 71,
                "qualidade_prior": "baixa_amostra",
                "amostra_prior": 6,
                "prior_ranking": -3.0,
            },
        }

        with patch("scheduler.log_event") as mocked_log_event:
            self._run_cycle(
                jogos,
                prior,
                {"aprovado": False, "reason_code": "gate_block", "bloqueado_em": "gate3"},
                mocked_log_event=mocked_log_event,
            )

        reject_calls = [
            c.args
            for c in mocked_log_event.call_args_list
            if len(c.args) >= 6 and c.args[0] == "runtime" and c.args[1] == "gate" and c.args[3] == "reject"
        ]
        self.assertTrue(reject_calls)
        detalhes = reject_calls[0][5]
        self.assertIn("qualidade_prior", detalhes)
        self.assertIn("amostra_prior", detalhes)
        self.assertIn("ajuste_prior", detalhes)


if __name__ == "__main__":
    unittest.main()
