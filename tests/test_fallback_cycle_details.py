import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import scheduler
from data import database


class TestFallbackCycleDetailsDB(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="edge-fallback-test-")
        self.tmp_db = os.path.join(self.tmp_dir, "edge_protocol_test.db")
        self.original_db_path = database.DB_PATH
        database.DB_PATH = self.tmp_db
        database.criar_banco()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_registrar_fallback_cycle_detail_insercao_sucesso(self):
        database.registrar_fallback_cycle_detail(
            job_nome="analise",
            janela_chave="2026-04-02T12:00",
            liga="Premier League",
            jogo="Arsenal vs Chelsea",
            mercado="1x2_casa",
            motivo_fallback="fallback_stats_medias",
            detalhes={"fonte_dados": "medias", "source_quality": "fallback"},
        )

        conn = sqlite3.connect(database.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT job_nome, janela_chave, liga, jogo, mercado, motivo_fallback
            FROM fallback_cycle_details
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "analise")
        self.assertEqual(row[1], "2026-04-02T12:00")
        self.assertEqual(row[2], "Premier League")
        self.assertEqual(row[3], "Arsenal vs Chelsea")
        self.assertEqual(row[4], "1x2_casa")
        self.assertEqual(row[5], "fallback_stats_medias")


class TestFallbackCycleDetailsSchedulerTriggers(unittest.TestCase):
    def test_trigger_gravacao_fallback_stats_medias(self):
        scheduler.EXECUCAO_CICLO["job_nome"] = "analise"
        scheduler.EXECUCAO_CICLO["janela_chave"] = "2026-04-02T12:00"

        jogo = {"liga": "Premier League", "jogo": "Arsenal vs Chelsea"}
        with patch.object(scheduler.FALLBACK_SERVICE, "persist_fallback_detail") as mocked:
            scheduler.registrar_fallback_stats_medias(
                jogo=jogo,
                mercado="under_2.5",
                fonte_dados="medias",
                source_quality="fallback",
            )

        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["job_nome"], "analise")
        self.assertEqual(kwargs["janela_chave"], "2026-04-02T12:00")
        self.assertEqual(kwargs["liga"], "Premier League")
        self.assertEqual(kwargs["jogo"], "Arsenal vs Chelsea")
        self.assertEqual(kwargs["mercado"], "under_2.5")
        self.assertEqual(kwargs["motivo_fallback"], "fallback_stats_medias")

    def test_trigger_gravacao_source_quality_low(self):
        scheduler.EXECUCAO_CICLO["job_nome"] = "analise"
        scheduler.EXECUCAO_CICLO["janela_chave"] = "2026-04-02T12:05"

        jogo = {"liga": "Premier League", "jogo": "Liverpool vs Chelsea"}
        with patch.object(scheduler.FALLBACK_SERVICE, "persist_fallback_detail") as mocked:
            scheduler.registrar_fallback_source_quality_low(
                jogo=jogo,
                mercado="1x2_fora",
                fonte_dados="xG+SOS",
                source_quality="fallback",
            )

        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["job_nome"], "analise")
        self.assertEqual(kwargs["janela_chave"], "2026-04-02T12:05")
        self.assertEqual(kwargs["liga"], "Premier League")
        self.assertEqual(kwargs["jogo"], "Liverpool vs Chelsea")
        self.assertEqual(kwargs["mercado"], "1x2_fora")
        self.assertEqual(kwargs["motivo_fallback"], "source_quality_low")


if __name__ == "__main__":
    unittest.main()
