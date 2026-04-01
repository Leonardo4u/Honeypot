import csv
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "model"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

import clv_brier
from picks_log import PickLogger


class TestClvBrierPicksLogIntegration(unittest.TestCase):
    def test_atualizar_clv_atualiza_closing_odds_no_picks_log(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "edge_protocol.db")
            picks_path = os.path.join(td, "picks_log.csv")

            logger = PickLogger(picks_path)
            prediction_id = "pred-777"
            logger.append_pick(
                prediction_id=prediction_id,
                league="Premier League",
                market="1x2_casa",
                match_name="Arsenal vs Chelsea",
                odds_at_pick=2.0,
                implied_prob=0.5,
                raw_prob_model=0.55,
                calibrated_prob_model=0.55,
                calibrator_fitted=True,
                confidence_dados=70,
                estabilidade_odd=70,
                contexto_jogo=70,
                edge_score=80,
                kelly_fraction=0.01,
                kelly_stake=10,
                bank_used=1000,
                recomendacao_acao="BET",
                reasoning_trace={"fatores_descartados": []},
            )

            horario = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE sinais (
                    id INTEGER PRIMARY KEY,
                    liga TEXT,
                    jogo TEXT,
                    horario TEXT,
                    prediction_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE clv_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sinal_id INTEGER,
                    jogo TEXT,
                    mercado TEXT,
                    odd_entrada REAL,
                    odd_fechamento REAL,
                    clv_percentual REAL,
                    timestamp_entrada TEXT,
                    timestamp_fechamento TEXT,
                    status TEXT DEFAULT 'aguardando',
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO sinais (id, liga, jogo, horario, prediction_id) VALUES (777, 'Premier League', 'Arsenal vs Chelsea', ?, ?)",
                (horario, prediction_id),
            )
            conn.execute(
                "INSERT INTO clv_tracking (sinal_id, jogo, mercado, odd_entrada, status) VALUES (777, 'Arsenal vs Chelsea', '1x2_casa', 2.0, 'aguardando')"
            )
            conn.commit()
            conn.close()

            old_pick_path = clv_brier.PICKS_LOG_PATH
            try:
                clv_brier.PICKS_LOG_PATH = picks_path
                clv = clv_brier.atualizar_clv(777, odd_fechamento=1.9, outcome=1, db_path=db_path)
                self.assertIsNotNone(clv)

                with open(picks_path, "r", newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(rows[0]["outcome"], "1")
                self.assertEqual(rows[0]["closing_odds"], "1.9")
            finally:
                clv_brier.PICKS_LOG_PATH = old_pick_path


if __name__ == "__main__":
    unittest.main()
