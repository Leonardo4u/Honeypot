import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from data import database, quality_prior
from data.forma_recente import calcular_confianca_contexto, calcular_confianca_dados


class TestConfidenceQualityPrior(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "edge_protocol_test.db")
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                liga TEXT,
                jogo TEXT,
                mercado TEXT,
                odd REAL,
                ev_estimado REAL,
                edge_score INTEGER,
                stake_unidades REAL,
                status TEXT,
                resultado TEXT,
                lucro_unidades REAL,
                fonte TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _insert_sinal(self, liga, mercado, jogo, resultado, lucro, fonte="historico"):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO sinais (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades,
                                status, resultado, lucro_unidades, fonte)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-20",
                liga,
                jogo,
                mercado,
                1.9,
                0.08,
                75,
                1.0,
                "finalizado",
                resultado,
                lucro,
                fonte,
            ),
        )
        conn.commit()
        conn.close()

    def test_prior_sem_sinal(self):
        with patch.object(database, "DB_PATH", self.db_path):
            prior = quality_prior.calcular_prior_qualidade_mercado_liga("Premier League", "1x2_casa", amostra_minima=10)

        self.assertEqual(prior["qualidade"], "sem_sinal")
        self.assertEqual(prior["amostra"], 0)

    def test_prior_baixa_amostra(self):
        for i in range(4):
            self._insert_sinal("Premier League", "1x2_casa", f"A{i} vs B{i}", "verde", 0.9)

        with patch.object(database, "DB_PATH", self.db_path):
            prior = quality_prior.calcular_prior_qualidade_mercado_liga("Premier League", "1x2_casa", amostra_minima=10)

        self.assertEqual(prior["qualidade"], "baixa_amostra")
        self.assertEqual(prior["amostra"], 4)

    def test_prior_ok(self):
        for i in range(12):
            resultado = "verde" if i < 8 else "vermelho"
            lucro = 0.9 if resultado == "verde" else -1.0
            self._insert_sinal("Premier League", "1x2_casa", f"C{i} vs D{i}", resultado, lucro)

        with patch.object(database, "DB_PATH", self.db_path):
            prior = quality_prior.calcular_prior_qualidade_mercado_liga("Premier League", "1x2_casa", amostra_minima=10)

        self.assertEqual(prior["qualidade"], "ok")
        self.assertEqual(prior["amostra"], 12)
        self.assertGreater(prior["prior_ranking"], 0)

    def test_confianca_contexto_preserva_proveniencia_e_contrato(self):
        for i in range(6):
            self._insert_sinal("Premier League", "1x2_casa", f"Arsenal vs Team{i}", "verde", 0.9)
            self._insert_sinal("Premier League", "1x2_casa", f"Team{i} vs Chelsea", "verde", 0.9)

        with patch.object(database, "DB_PATH", self.db_path), patch("data.forma_recente.DB_PATH", self.db_path), patch(
            "data.forma_recente.carregar_medias_safe", return_value={"Arsenal": {}, "Chelsea": {}}
        ):
            contexto = calcular_confianca_contexto("Arsenal", "Chelsea", "Premier League", "1x2_casa")
            contexto_sem_prior_explicito = calcular_confianca_contexto("Arsenal", "Chelsea")
            conf = calcular_confianca_dados("Arsenal", "Chelsea")

        self.assertIn("qualidade_prior", contexto)
        self.assertIn("amostra_prior", contexto)
        self.assertEqual(conf, contexto_sem_prior_explicito["confianca"])
        self.assertGreaterEqual(contexto["confianca"], conf)
        self.assertGreaterEqual(conf, 50)


if __name__ == "__main__":
    unittest.main()
