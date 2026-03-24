import os
import shutil
import sqlite3
import tempfile
import unittest

from data import database


class TestDatabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="edge-db-test-")
        self.tmp_db = os.path.join(self.tmp_dir, "edge_protocol_test.db")
        self.original_db_path = database.DB_PATH
        database.DB_PATH = self.tmp_db
        database.criar_banco()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_inserir_sinal_persiste_e_retorna_id_valido(self):
        sinal_id = database.inserir_sinal(
            liga="Premier League",
            jogo="Arsenal vs Chelsea",
            mercado="1x2_casa",
            odd=1.92,
            ev=0.10,
            score=80,
            stake=1.0,
            message_id_vip=123,
            message_id_free=456,
            horario="2026-03-24T17:30:00Z",
        )

        self.assertIsInstance(sinal_id, int)
        self.assertGreater(sinal_id, 0)

        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT jogo, mercado, status FROM sinais WHERE id = ?", (sinal_id,))
        row = c.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Arsenal vs Chelsea")
        self.assertEqual(row[1], "1x2_casa")
        self.assertEqual(row[2], "pendente")

    def test_atualizar_resultado_atualiza_campos_esperados(self):
        sinal_id = database.inserir_sinal(
            liga="Premier League",
            jogo="Arsenal vs Chelsea",
            mercado="1x2_casa",
            odd=1.92,
            ev=0.10,
            score=80,
            stake=1.0,
        )

        database.atualizar_resultado(sinal_id, "verde", 0.92)

        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT status, resultado, lucro_unidades FROM sinais WHERE id = ?", (sinal_id,))
        row = c.fetchone()
        conn.close()

        self.assertEqual(row[0], "finalizado")
        self.assertEqual(row[1], "verde")
        self.assertAlmostEqual(row[2], 0.92, places=2)

    def test_sinal_existe_consistente_antes_e_depois_da_atualizacao(self):
        sinal_id = database.inserir_sinal(
            liga="Premier League",
            jogo="Arsenal vs Chelsea",
            mercado="1x2_casa",
            odd=1.92,
            ev=0.10,
            score=80,
            stake=1.0,
        )

        self.assertTrue(database.sinal_existe(sinal_id))

        database.atualizar_resultado(sinal_id, "vermelho", -1.0)

        self.assertTrue(database.sinal_existe(sinal_id))
        self.assertFalse(database.sinal_existe(sinal_id + 9999))

    def test_schema_sinais_contem_colunas_fixture_identity(self):
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(sinais)")
        colunas = {row[1] for row in c.fetchall()}
        conn.close()

        self.assertIn("fixture_id_api", colunas)
        self.assertIn("fixture_data_api", colunas)

    def test_atualizar_fixture_referencia_persiste_campos(self):
        sinal_id = database.inserir_sinal(
            liga="Premier League",
            jogo="Arsenal vs Chelsea",
            mercado="1x2_casa",
            odd=1.92,
            ev=0.10,
            score=80,
            stake=1.0,
        )

        database.atualizar_fixture_referencia(
            sinal_id=sinal_id,
            fixture_id_api="123456",
            fixture_data_api="2026-03-20",
        )

        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT fixture_id_api, fixture_data_api FROM sinais WHERE id = ?",
            (sinal_id,),
        )
        row = c.fetchone()
        conn.close()

        self.assertEqual(row[0], "123456")
        self.assertEqual(row[1], "2026-03-20")


if __name__ == "__main__":
    unittest.main()
