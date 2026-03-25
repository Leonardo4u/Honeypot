import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from data import quality_telemetry


class TestQualityTelemetryWeekly(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "quality_test.db")
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            '''
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                data TEXT,
                liga TEXT,
                mercado TEXT,
                status TEXT,
                resultado TEXT,
                lucro_unidades REAL
            )
            '''
        )
        c.execute(
            '''
            CREATE TABLE brier_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sinal_id INTEGER,
                brier_score REAL
            )
            '''
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _insert_sinal(self, sinal_id, data_ref, liga, mercado, resultado, lucro):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO sinais (id, data, liga, mercado, status, resultado, lucro_unidades)
            VALUES (?, ?, ?, ?, 'finalizado', ?, ?)
            """,
            (sinal_id, data_ref, liga, mercado, resultado, lucro),
        )
        conn.commit()
        conn.close()

    def _insert_brier(self, sinal_id, score):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO brier_tracking (sinal_id, brier_score) VALUES (?, ?)", (sinal_id, score))
        conn.commit()
        conn.close()

    def test_snapshot_semanal_persiste_segmentacao(self):
        self._insert_sinal(1, "2026-03-20", "Premier League", "1x2_casa", "verde", 0.8)
        self._insert_sinal(2, "2026-03-21", "Premier League", "over_2.5", "vermelho", -1.0)
        self._insert_sinal(3, "2026-03-25", "UEFA Champions League", "1x2_casa", "verde", 1.2)
        self._insert_brier(1, 0.18)
        self._insert_brier(2, 0.32)
        self._insert_brier(3, 0.12)

        snapshot = quality_telemetry.registrar_snapshot_qualidade_semanal(
            db_path=self.db_path,
            referencia="2026-03-25",
        )

        self.assertEqual(snapshot["referencia_semana"], "2026-03-25")
        segmentos = snapshot["segmentos"]
        global_seg = [s for s in segmentos if s["segmento_tipo"] == "global"][0]
        self.assertEqual(global_seg["total_apostas"], 3)
        self.assertIn("win_rate", global_seg)
        self.assertIn("brier_medio", global_seg)

        mercados = [s["segmento_valor"] for s in segmentos if s["segmento_tipo"] == "mercado"]
        self.assertIn("1x2_casa", mercados)
        self.assertIn("over_2.5", mercados)

        historico = quality_telemetry.listar_historico_qualidade(db_path=self.db_path)
        self.assertEqual(len(historico), 1)
        self.assertEqual(historico[0]["referencia_semana"], "2026-03-25")

    def test_historico_retorna_ordenado_por_referencia(self):
        quality_telemetry.persistir_snapshot_qualidade(
            {
                "referencia_semana": "2026-03-18",
                "segmentos": [
                    {
                        "segmento_tipo": "global",
                        "segmento_valor": "all",
                        "total_apostas": 4,
                        "win_rate": 0.5,
                        "roi_pct": 1.0,
                        "brier_medio": 0.24,
                        "fallback_rate": 0.1,
                    }
                ],
            },
            db_path=self.db_path,
        )
        quality_telemetry.persistir_snapshot_qualidade(
            {
                "referencia_semana": "2026-03-25",
                "segmentos": [
                    {
                        "segmento_tipo": "global",
                        "segmento_valor": "all",
                        "total_apostas": 5,
                        "win_rate": 0.4,
                        "roi_pct": -2.0,
                        "brier_medio": 0.29,
                        "fallback_rate": 0.2,
                    }
                ],
            },
            db_path=self.db_path,
        )

        historico = quality_telemetry.listar_historico_qualidade(db_path=self.db_path, limite=10)
        self.assertEqual([h["referencia_semana"] for h in historico], ["2026-03-18", "2026-03-25"])

    def test_drift_rolling_dispara_quando_degradacao_persistente(self):
        for referencia, brier, wr in [
            ("2026-03-04", 0.28, 0.47),
            ("2026-03-11", 0.29, 0.46),
            ("2026-03-18", 0.30, 0.45),
            ("2026-03-25", 0.31, 0.44),
        ]:
            quality_telemetry.persistir_snapshot_qualidade(
                {
                    "referencia_semana": referencia,
                    "segmentos": [
                        {
                            "segmento_tipo": "global",
                            "segmento_valor": "all",
                            "total_apostas": 6,
                            "win_rate": wr,
                            "roi_pct": -5.0,
                            "brier_medio": brier,
                            "fallback_rate": 0.2,
                        }
                    ],
                },
                db_path=self.db_path,
            )

        alerta = quality_telemetry.avaliar_drift_historico(
            db_path=self.db_path,
            janela=4,
            min_persistencia=3,
            brier_limite=0.25,
            win_rate_limite=0.50,
        )
        self.assertTrue(alerta)
        self.assertEqual(alerta["metrica"], "brier_medio")

    def test_drift_rolling_nao_dispara_por_ruido_isolado(self):
        for referencia, brier, wr in [
            ("2026-03-04", 0.20, 0.53),
            ("2026-03-11", 0.21, 0.52),
            ("2026-03-18", 0.31, 0.44),
            ("2026-03-25", 0.21, 0.54),
        ]:
            quality_telemetry.persistir_snapshot_qualidade(
                {
                    "referencia_semana": referencia,
                    "segmentos": [
                        {
                            "segmento_tipo": "global",
                            "segmento_valor": "all",
                            "total_apostas": 5,
                            "win_rate": wr,
                            "roi_pct": 1.0,
                            "brier_medio": brier,
                            "fallback_rate": 0.1,
                        }
                    ],
                },
                db_path=self.db_path,
            )

        alerta = quality_telemetry.avaliar_drift_historico(
            db_path=self.db_path,
            janela=4,
            min_persistencia=3,
            brier_limite=0.25,
            win_rate_limite=0.50,
        )
        self.assertIsNone(alerta)


class TestSchedulerWeeklyTelemetryIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "schedule" not in sys.modules:
            sys.modules["schedule"] = types.ModuleType("schedule")

        if "telegram" not in sys.modules:
            telegram_stub = types.ModuleType("telegram")

            class _BotStub:
                def __init__(self, *args, **kwargs):
                    pass

                async def send_message(self, *args, **kwargs):
                    return None

            telegram_stub.Bot = _BotStub
            sys.modules["telegram"] = telegram_stub

        if "dotenv" not in sys.modules:
            dotenv_stub = types.ModuleType("dotenv")
            dotenv_stub.load_dotenv = lambda *args, **kwargs: True
            sys.modules["dotenv"] = dotenv_stub

        if "requests" not in sys.modules:
            requests_stub = types.ModuleType("requests")
            requests_stub.get = lambda *args, **kwargs: None
            requests_stub.Timeout = Exception
            requests_stub.ConnectionError = Exception
            sys.modules["requests"] = requests_stub

        if "numpy" not in sys.modules:
            numpy_stub = types.ModuleType("numpy")
            numpy_stub.zeros = lambda shape: [[0.0] * shape[1] for _ in range(shape[0])]
            numpy_stub.mean = lambda values: sum(values) / len(values) if values else 0.0
            sys.modules["numpy"] = numpy_stub

        if "scipy" not in sys.modules:
            scipy_stub = types.ModuleType("scipy")
            scipy_stats_stub = types.ModuleType("scipy.stats")
            scipy_optimize_stub = types.ModuleType("scipy.optimize")
            scipy_stats_stub.poisson = types.SimpleNamespace(pmf=lambda *args, **kwargs: 0.0)
            scipy_optimize_stub.minimize = lambda *args, **kwargs: types.SimpleNamespace(x=[0.0], success=True)
            scipy_stub.stats = scipy_stats_stub
            scipy_stub.optimize = scipy_optimize_stub
            sys.modules["scipy"] = scipy_stub
            sys.modules["scipy.stats"] = scipy_stats_stub
            sys.modules["scipy.optimize"] = scipy_optimize_stub

        global scheduler
        import scheduler  # noqa: F401

    def test_job_semanal_registra_snapshot_sem_quebrar_fluxo(self):
        fake_xg = types.ModuleType("xg_understat")
        fake_xg.atualizar_xg_todas_ligas = lambda: None

        with patch.dict(sys.modules, {"xg_understat": fake_xg}, clear=False):
            with patch("scheduler.atualizar_todas_ligas") as mock_stats, patch(
                "scheduler.registrar_snapshot_qualidade_semanal",
                return_value={"referencia_semana": "2026-03-25", "segmentos": [{}, {}]},
            ) as mock_snapshot, patch("scheduler.avaliar_drift_historico", return_value=None), patch(
                "scheduler.log_event"
            ):
                scheduler.atualizar_stats_semanalmente()

        mock_stats.assert_called_once()
        mock_snapshot.assert_called_once()

    def test_job_semanal_trata_falha_snapshot_com_degradado(self):
        fake_xg = types.ModuleType("xg_understat")
        fake_xg.atualizar_xg_todas_ligas = lambda: None

        with patch.dict(sys.modules, {"xg_understat": fake_xg}, clear=False):
            with patch("scheduler.atualizar_todas_ligas"), patch(
                "scheduler.registrar_snapshot_qualidade_semanal",
                side_effect=RuntimeError("db_offline"),
            ), patch("scheduler.avaliar_drift_historico", return_value=None), patch(
                "scheduler.marcar_ciclo_degradado"
            ) as mock_degradado:
                scheduler.atualizar_stats_semanalmente()

        self.assertTrue(mock_degradado.called)

    def test_job_semanal_dispara_alerta_rolling(self):
        fake_xg = types.ModuleType("xg_understat")
        fake_xg.atualizar_xg_todas_ligas = lambda: None

        alerta = {
            "metrica": "brier_medio",
            "segmento_tipo": "global",
            "segmento_valor": "all",
            "periodo_inicio": "2026-03-11",
            "periodo_fim": "2026-03-25",
            "min_persistencia": 3,
            "valor_atual": 0.29,
        }

        with patch.dict(sys.modules, {"xg_understat": fake_xg}, clear=False):
            with patch("scheduler.atualizar_todas_ligas"), patch(
                "scheduler.registrar_snapshot_qualidade_semanal",
                return_value={"referencia_semana": "2026-03-25", "segmentos": [{}, {}]},
            ), patch("scheduler.avaliar_drift_historico", return_value=alerta), patch(
                "scheduler.enviar_alerta_drift_historico"
            ) as mock_send, patch("scheduler.log_event"):
                scheduler.atualizar_stats_semanalmente()

        mock_send.assert_called_once_with(alerta)


if __name__ == "__main__":
    unittest.main()
