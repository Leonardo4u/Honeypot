import asyncio
import csv
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import scheduler
from data import database
from model.picks_log import PickLogger


class TestDuplicateSignalQueries(unittest.TestCase):
    def setUp(self):
        self._old_db_path = database.DB_PATH
        self._old_wal_paths = set(database._WAL_CONFIGURED_PATHS)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "edge_protocol.db")
        database.DB_PATH = self.db_path
        database._WAL_CONFIGURED_PATHS.discard(self.db_path)
        database.criar_banco()

    def tearDown(self):
        database.DB_PATH = self._old_db_path
        database._WAL_CONFIGURED_PATHS.clear()
        database._WAL_CONFIGURED_PATHS.update(self._old_wal_paths)
        self.tmpdir.cleanup()

    def _insert_sinal(self, created_at, market="1x2_casa"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO sinais (
                data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-01",
                "Brasileirao Serie A",
                "Flamengo vs Palmeiras",
                market,
                1.95,
                0.10,
                80,
                1.0,
                created_at,
            ),
        )
        conn.commit()
        conn.close()

    def test_signal_blocked_when_same_game_market_exists_today(self):
        self._insert_sinal("2026-04-01T10:00:00Z", market="1x2_casa")
        count = database.contar_sinais_duplicados_mesmo_dia(
            "Brasileirao Serie A", "Flamengo", "Palmeiras", "1x2_casa", data_ref="2026-04-01"
        )
        self.assertGreater(count, 0)

    def test_signal_allowed_when_same_game_different_day(self):
        self._insert_sinal("2026-03-31T23:59:00Z", market="1x2_casa")
        count = database.contar_sinais_duplicados_mesmo_dia(
            "Brasileirao Serie A", "Flamengo", "Palmeiras", "1x2_casa", data_ref="2026-04-01"
        )
        self.assertEqual(count, 0)

    def test_signal_allowed_when_same_game_different_market(self):
        self._insert_sinal("2026-04-01T10:00:00Z", market="over_2.5")
        count = database.contar_sinais_duplicados_mesmo_dia(
            "Brasileirao Serie A", "Flamengo", "Palmeiras", "1x2_casa", data_ref="2026-04-01"
        )
        self.assertEqual(count, 0)


class TestSchedulerDuplicateSkip(unittest.TestCase):
    def test_scheduler_skips_duplicate_before_telegram_send(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "edge_protocol.db")
            data_dir = os.path.join(td, "data")
            os.makedirs(data_dir, exist_ok=True)

            old_sched_db = scheduler.DB_PATH
            old_db_db = database.DB_PATH
            old_bot_data_dir = scheduler.BOT_DATA_DIR
            old_bot_data = os.environ.get("BOT_DATA_DIR")
            old_ready = scheduler._DB_SCHEMA_READY

            scheduler.DB_PATH = db_path
            database.DB_PATH = db_path
            scheduler.BOT_DATA_DIR = data_dir
            scheduler._DB_SCHEMA_READY = False
            os.environ["BOT_DATA_DIR"] = data_dir

            database._WAL_CONFIGURED_PATHS.discard(db_path)
            database.criar_banco()

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                INSERT INTO sinais (
                    data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-03-15",
                    "Brasileirao Serie A",
                    "Flamengo vs Palmeiras",
                    "1x2_casa",
                    1.9,
                    0.1,
                    75,
                    1.0,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
            conn.commit()
            conn.close()

            send_count = {"n": 0}

            class _BotStub:
                async def send_message(self, *args, **kwargs):
                    send_count["n"] += 1
                    return SimpleNamespace(message_id=123)

            jogos = [
                {
                    "home_team": "Flamengo",
                    "away_team": "Palmeiras",
                    "jogo": "Flamengo vs Palmeiras",
                    "liga": "Brasileirao Serie A",
                    "horario": "2026-04-01T18:00:00Z",
                    "odds": {
                        "casa": 1.9,
                        "fora": 3.2,
                        "over_2.5": 2.0,
                        "under_2.5": 1.8,
                    },
                }
            ]

            try:
                with patch.object(scheduler, "LIGAS", ["soccer_brazil_campeonato"]), \
                     patch("scheduler.Bot", return_value=_BotStub()), \
                     patch("scheduler.buscar_sinais_hoje", return_value=[]), \
                     patch("scheduler.buscar_jogos_com_odds_com_status", return_value={"status": "ok", "data": []}), \
                     patch("scheduler.formatar_jogos", return_value=jogos), \
                     patch("scheduler.obter_media_gols", return_value=(1.4, 1.0, "xG+SOS")), \
                     patch("scheduler.calcular_ajuste_forma", return_value=(0.0, 0.0)), \
                     patch("scheduler.calcular_confianca_contexto", return_value={
                         "confianca": 70,
                         "qualidade_prior": "ok",
                         "amostra_prior": 100,
                         "prior_ranking": 0.0,
                     }), \
                     patch("scheduler.analisar_jogo", return_value={
                         "decisao": "APOSTAR",
                         "ev": 0.11,
                         "edge_score": 80,
                         "odd": 1.9,
                         "liga": "Brasileirao Serie A",
                         "jogo": "Flamengo vs Palmeiras",
                         "mercado": "1x2_casa",
                         "prob_modelo": 0.58,
                         "prob_modelo_base": 0.58,
                         "prediction_id": "pred-dup",
                     }), \
                     patch("scheduler.buscar_odds_todas_casas", return_value=None), \
                     patch("scheduler.aplicar_triple_gate", return_value={"aprovado": True, "penalizacao_score": 0}), \
                     patch("scheduler.contar_sinais_abertos", return_value=0), \
                     patch("scheduler.contar_sinais_liga_hoje", return_value=0), \
                     patch("scheduler.contar_sinais_mesmo_jogo_abertos", return_value=0), \
                     patch("scheduler.calcular_kelly", return_value={
                         "aprovado": True,
                         "tier": "normal",
                         "kelly_final_pct": 1.0,
                         "valor_reais": 10.0,
                     }), \
                     patch("scheduler.formatar_sinal_kelly", return_value="sinal"), \
                     patch("scheduler.atualizar_excel"):
                    asyncio.run(scheduler.processar_jogos(dry_run=False))

                self.assertEqual(send_count["n"], 0)
                log_path = os.path.join(td, "logs", "duplicates_skipped.log")
                self.assertTrue(os.path.exists(log_path))
                with open(log_path, "r", encoding="utf-8") as f:
                    line = f.readline().strip()
                payload = json.loads(line)
                self.assertEqual(payload.get("reason"), "duplicate_same_day")
                self.assertEqual(payload.get("league"), "Brasileirao Serie A")
                self.assertEqual(payload.get("market"), "1x2_casa")
            finally:
                scheduler.DB_PATH = old_sched_db
                database.DB_PATH = old_db_db
                scheduler.BOT_DATA_DIR = old_bot_data_dir
                scheduler._DB_SCHEMA_READY = old_ready
                if old_bot_data is None:
                    os.environ.pop("BOT_DATA_DIR", None)
                else:
                    os.environ["BOT_DATA_DIR"] = old_bot_data


class TestPicksLogDedup(unittest.TestCase):
    def test_picks_log_dedup_same_day(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "picks_log.csv")
            logger = PickLogger(csv_path)

            first = logger.append_pick(
                prediction_id="pred-1",
                league="Brasileirao Serie A",
                market="1x2_casa",
                match_name="Flamengo vs Palmeiras",
                odds_at_pick=1.9,
                implied_prob=0.52,
                raw_prob_model=0.56,
                calibrated_prob_model=0.55,
                calibrator_fitted=True,
                confidence_dados=70,
                estabilidade_odd=70,
                contexto_jogo=70,
                edge_score=80,
                kelly_fraction=0.01,
                kelly_stake=10.0,
                bank_used=1000.0,
                recomendacao_acao="BET",
                reasoning_trace={},
            )
            second = logger.append_pick(
                prediction_id="pred-2",
                league="Brasileirao Serie A",
                market="1x2_casa",
                match_name="Flamengo vs Palmeiras",
                odds_at_pick=1.92,
                implied_prob=0.53,
                raw_prob_model=0.57,
                calibrated_prob_model=0.56,
                calibrator_fitted=True,
                confidence_dados=71,
                estabilidade_odd=70,
                contexto_jogo=70,
                edge_score=81,
                kelly_fraction=0.01,
                kelly_stake=10.0,
                bank_used=1000.0,
                recomendacao_acao="BET",
                reasoning_trace={},
            )

            self.assertTrue(first)
            self.assertFalse(second)

            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
