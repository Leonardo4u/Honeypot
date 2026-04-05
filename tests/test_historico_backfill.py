import os
import shutil
import sqlite3
import tempfile
import unittest

import pandas as pd

import calibrar_modelo
from data import database
from model import poisson
from data import xg_understat


class TestHistoricoSchemaSafety(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="edge-historico-schema-")
        self.tmp_db = os.path.join(self.tmp_dir, "edge_protocol_test.db")
        self.old_db_path = database.DB_PATH
        database.DB_PATH = self.tmp_db
        database.criar_banco()

    def tearDown(self):
        database.DB_PATH = self.old_db_path
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sinais_tem_coluna_fonte(self):
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(sinais)")
        cols = {row[1]: row[4] for row in c.fetchall()}
        conn.close()

        self.assertIn("fonte", cols)
        self.assertEqual(cols["fonte"], "'bot'")

    def test_duplicado_historico_bloqueado_por_indice(self):
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()

        payload = (
            "2026-03-24",
            "Premier League",
            "Arsenal vs Chelsea",
            "over_2.5",
            1.95,
            0.10,
            75,
            1.0,
            "finalizado",
            "verde",
            0.95,
            "historico",
        )

        c.execute(
            """
            INSERT INTO sinais
            (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades,
             status, resultado, lucro_unidades, fonte)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            payload,
        )

        c.execute(
            """
            INSERT OR IGNORE INTO sinais
            (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades,
             status, resultado, lucro_unidades, fonte)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            payload,
        )
        conn.commit()

        c.execute("SELECT COUNT(*) FROM sinais WHERE fonte='historico'")
        total_hist = c.fetchone()[0]
        conn.close()

        self.assertEqual(total_hist, 1)


class TestHistoricoBackfillFlow(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="edge-historico-flow-")
        self.tmp_db = os.path.join(self.tmp_dir, "edge_protocol_test.db")

        self.old_calib_db = calibrar_modelo.DB_PATH
        self.old_data_db = database.DB_PATH

        calibrar_modelo.DB_PATH = self.tmp_db
        database.DB_PATH = self.tmp_db
        database.criar_banco()

        self.old_xg = xg_understat.calcular_media_gols_com_xg
        self.old_prob = poisson.calcular_probabilidades
        self.old_ou = poisson.calcular_prob_over_under

        def fake_xg(*_args, **_kwargs):
            return 1.4, 1.1, "medias"

        def fake_prob(*_args, **_kwargs):
            return {"prob_casa": 0.6, "prob_empate": 0.2, "prob_fora": 0.2}

        def fake_ou(*_args, **_kwargs):
            return {"prob_over": 0.7, "prob_under": 0.3, "linha": 2.5}

        xg_understat.calcular_media_gols_com_xg = fake_xg
        poisson.calcular_probabilidades = fake_prob
        poisson.calcular_prob_over_under = fake_ou

        self.df = pd.DataFrame(
            [
                {
                    "liga": "Premier League",
                    "time_casa": "Arsenal",
                    "time_fora": "Chelsea",
                    "gols_casa": 2,
                    "gols_fora": 1,
                    "odd_over25": 1.95,
                    "data_jogo": "2026-03-24",
                },
                {
                    "liga": "La Liga",
                    "time_casa": "Real Madrid",
                    "time_fora": "Barcelona",
                    "gols_casa": 1,
                    "gols_fora": 2,
                    "odd_over25": 2.05,
                    "data_jogo": "2026-03-25",
                },
            ]
        )

    def tearDown(self):
        calibrar_modelo.DB_PATH = self.old_calib_db
        database.DB_PATH = self.old_data_db
        xg_understat.calcular_media_gols_com_xg = self.old_xg
        poisson.calcular_probabilidades = self.old_prob
        poisson.calcular_prob_over_under = self.old_ou
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_primeira_execucao_insere_historico(self):
        resumo = calibrar_modelo.popular_banco_historico(self.df, n_max=10)

        self.assertEqual(resumo["falhas"], 0)
        self.assertGreaterEqual(resumo["inseridos"], 1)

        conn = sqlite3.connect(self.tmp_db)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sinais WHERE fonte='historico'")
        total = c.fetchone()[0]
        conn.close()

        self.assertGreaterEqual(total, 1)

    def test_rerun_nao_duplica_e_conta_duplicados(self):
        primeiro = calibrar_modelo.popular_banco_historico(self.df, n_max=10)
        segundo = calibrar_modelo.popular_banco_historico(self.df, n_max=10)

        self.assertGreaterEqual(primeiro["inseridos"], 1)
        self.assertGreaterEqual(segundo["duplicados"], 1)

        conn = sqlite3.connect(self.tmp_db)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sinais WHERE fonte='historico'")
        total_hist = c.fetchone()[0]
        conn.close()

        self.assertEqual(total_hist, primeiro["inseridos"])

    def test_falha_linha_isolada_nao_aborta_lote(self):
        original_odd = calibrar_modelo._odd_valida

        def odd_with_failure(valor):
            if valor == "boom":
                raise ValueError("linha invalida")
            return original_odd(valor)

        calibrar_modelo._odd_valida = odd_with_failure
        try:
            df = pd.DataFrame(
                [
                    {
                        "liga": "Premier League",
                        "time_casa": "Arsenal",
                        "time_fora": "Chelsea",
                        "gols_casa": 2,
                        "gols_fora": 1,
                        "odd_over25": "boom",
                        "data_jogo": "2026-03-24",
                    },
                    {
                        "liga": "La Liga",
                        "time_casa": "Real Madrid",
                        "time_fora": "Barcelona",
                        "gols_casa": 1,
                        "gols_fora": 2,
                        "odd_over25": 2.05,
                        "data_jogo": "2026-03-25",
                    },
                ]
            )
            resumo = calibrar_modelo.popular_banco_historico(df, n_max=10)

            self.assertGreaterEqual(resumo["falhas"], 1)
            self.assertGreaterEqual(resumo["inseridos"], 1)
        finally:
            calibrar_modelo._odd_valida = original_odd


if __name__ == "__main__":
    unittest.main()
