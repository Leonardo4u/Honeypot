import csv
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model"
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from picks_log import PickLogger


class TestPickLogger(unittest.TestCase):
    def test_append_and_update_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "picks_log.csv")
            logger = PickLogger(path)

            logger.append_pick(
                prediction_id="abc-123",
                league="Premier League",
                market="1x2_casa",
                match_name="Arsenal vs Chelsea",
                odds_at_pick=2.0,
                implied_prob=0.5,
                raw_prob_model=0.56,
                calibrated_prob_model=0.54,
                calibrator_fitted=True,
                confidence_dados=72,
                estabilidade_odd=70,
                contexto_jogo=68,
                edge_score=81,
                kelly_fraction=0.02,
                kelly_stake=20,
                bank_used=1000,
                recomendacao_acao="BET",
                reasoning_trace={"fatores_descartados": []},
            )

            updated = logger.update_outcome("abc-123", outcome=1, closing_odds=1.95)
            self.assertTrue(updated)

            with open(path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["team_home"], "Arsenal")
            self.assertEqual(rows[0]["team_away"], "Chelsea")
            self.assertEqual(rows[0]["outcome"], "1")
            self.assertEqual(rows[0]["closing_odds"], "1.95")

    def _create_sinais_table(self, conn, with_prediction_id=True):
        """Cria schema minimo de sinais usado pelos testes de sync."""
        prediction_col = ", prediction_id TEXT" if with_prediction_id else ""
        conn.execute(
            f"""
            CREATE TABLE sinais (
                id INTEGER PRIMARY KEY,
                liga TEXT,
                jogo TEXT,
                resultado TEXT,
                odd REAL,
                status TEXT,
                horario TEXT,
                criado_em TEXT
                {prediction_col}
            )
            """
        )

    def test_sync_from_db_by_prediction_id(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "picks_log.csv")
            db_path = os.path.join(td, "edge_protocol.db")
            logger = PickLogger(csv_path)
            logger.append_pick(
                prediction_id="pred-001",
                league="Premier League",
                market="1x2_casa",
                match_name="Arsenal vs Chelsea",
                odds_at_pick=2.0,
                implied_prob=0.5,
                raw_prob_model=0.56,
                calibrated_prob_model=0.54,
                calibrator_fitted=True,
                confidence_dados=72,
                estabilidade_odd=70,
                contexto_jogo=68,
                edge_score=81,
                kelly_fraction=0.02,
                kelly_stake=20,
                bank_used=1000,
                recomendacao_acao="BET",
                reasoning_trace={"fatores_descartados": []},
            )

            conn = sqlite3.connect(db_path)
            self._create_sinais_table(conn, with_prediction_id=True)
            conn.execute(
                """
                INSERT INTO sinais (id, liga, jogo, resultado, odd, status, horario, criado_em, prediction_id)
                VALUES (1, 'Premier League', 'Arsenal vs Chelsea', 'verde', 1.88, 'finalizado',
                        '2026-03-28T12:00:00Z', '2026-03-28T12:00:00Z', 'pred-001')
                """
            )
            conn.commit()
            conn.close()

            summary = logger.sync_from_db(db_path)
            self.assertEqual(summary["total_finalizados"], 1)
            self.assertEqual(summary["matched"], 1)
            self.assertEqual(summary["updated"], 1)

            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["outcome"], "1")
            self.assertEqual(rows[0]["closing_odds"], "1.88")

    def test_sync_from_db_fallback_tuple_and_time(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = os.path.join(td, "picks_log.csv")
            db_path = os.path.join(td, "edge_protocol.db")
            logger = PickLogger(csv_path)
            logger.append_pick(
                prediction_id="pred-local",
                league="La Liga",
                market="1x2_fora",
                match_name="Barcelona vs Sevilla",
                odds_at_pick=2.2,
                implied_prob=0.45,
                raw_prob_model=0.48,
                calibrated_prob_model=0.47,
                calibrator_fitted=True,
                confidence_dados=69,
                estabilidade_odd=66,
                contexto_jogo=71,
                edge_score=79,
                kelly_fraction=0.01,
                kelly_stake=10,
                bank_used=1000,
                recomendacao_acao="BET",
                reasoning_trace={"fatores_descartados": []},
            )

            ts_csv = datetime(2026, 3, 28, 15, 0, 0, tzinfo=timezone.utc)
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            rows[0]["timestamp"] = ts_csv.isoformat()
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=PickLogger.FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)

            ts_db = (ts_csv + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn = sqlite3.connect(db_path)
            self._create_sinais_table(conn, with_prediction_id=False)
            conn.execute(
                """
                INSERT INTO sinais (id, liga, jogo, resultado, odd, status, horario, criado_em)
                VALUES (7, 'La Liga', 'Barcelona vs Sevilla', 'vermelho', 2.35, 'finalizado',
                        ?, ?)
                """,
                (ts_db, ts_db),
            )
            conn.commit()
            conn.close()

            summary = logger.sync_from_db(db_path)
            self.assertEqual(summary["matched"], 1)
            self.assertEqual(summary["updated"], 1)
            self.assertEqual(summary["unmatched"], 0)

            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["outcome"], "0")
            self.assertEqual(rows[0]["closing_odds"], "2.35")


if __name__ == "__main__":
    unittest.main()
