import asyncio
import csv
import importlib
import os
import sqlite3
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

import scheduler
from data import database
from model.picks_log import PickLogger


def _append_pick(csv_path: str, *, prediction_id: str = "pred-1", closing_odds: str | None = None):
    logger = PickLogger(csv_path)
    logger.append_pick(
        prediction_id=prediction_id,
        league="Premier League",
        market="1x2_casa",
        match_name="Arsenal vs Chelsea",
        odds_at_pick=1.92,
        implied_prob=0.52,
        raw_prob_model=0.55,
        calibrated_prob_model=0.56,
        calibrator_fitted=True,
        confidence_dados=70,
        estabilidade_odd=70,
        contexto_jogo=70,
        edge_score=80,
        kelly_fraction=0.02,
        kelly_stake=10.0,
        bank_used=1000.0,
        recomendacao_acao="BET",
        reasoning_trace={},
    )
    if closing_odds is not None:
        logger.update_outcome(prediction_id, 1, float(closing_odds))
    return logger


def test_enviar_resumo_diario_nao_quebra_com_module_not_found_error():
    bot = type("BotStub", (), {"send_message": AsyncMock(return_value=None)})()
    relatorio_fake = {
        "banca": {"atual": 1000.0, "drawdown_atual_pct": 0.0},
        "performance": {"roi_acumulado_pct": 0.0},
    }
    with patch("scheduler.Bot", return_value=bot), \
         patch("data.database.resumo_mensal", return_value=(0, 0, 0, 0.0)), \
         patch("data.database.resumo_calibracao", return_value={"faltam": 10, "total": 40}), \
         patch(
             "data.clv_brier.calcular_metricas",
             return_value={"total_apostas_clv": 0, "clv_medio": 0.0, "total_apostas_brier": 0, "brier_medio": 0.0},
         ), \
         patch("scheduler.gerar_relatorio_diario", return_value=relatorio_fake), \
         patch("scheduler.imprimir_relatorio", return_value=None), \
         patch("scheduler.atualizar_excel", return_value=None):
        asyncio.run(scheduler.enviar_resumo_diario())


def test_bootstrap_completo_db_path_cria_tabela_sinais(tmp_path):
    db_path = tmp_path / "custom.db"
    database.bootstrap_completo(db_path=str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sinais'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_sync_from_db_nao_sobrescreve_closing_odds_preenchido(tmp_path):
    csv_path = tmp_path / "picks.csv"
    db_path = tmp_path / "edge.db"
    logger = _append_pick(str(csv_path), closing_odds="1.75")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE sinais (
                id INTEGER,
                liga TEXT,
                jogo TEXT,
                resultado TEXT,
                odd REAL,
                prediction_id TEXT,
                horario TEXT,
                criado_em TEXT,
                data TEXT,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE clv_tracking (
                sinal_id INTEGER,
                odd_fechamento REAL
            )
            """
        )
        cur.execute(
            """
            INSERT INTO sinais VALUES (
                1, 'Premier League', 'Arsenal vs Chelsea', 'verde', 1.92, 'pred-1',
                '2026-04-04T10:00:00+00:00', '2026-04-04T10:00:01+00:00', '2026-04-04', 'finalizado'
            )
            """
        )
        cur.execute("INSERT INTO clv_tracking VALUES (1, 1.61)")
        conn.commit()
    finally:
        conn.close()

    logger.sync_from_db(str(db_path))

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["closing_odds"] == "1.75"


def test_sync_from_db_nao_quebra_com_uma_coluna_temporal(tmp_path):
    csv_path = tmp_path / "picks.csv"
    db_path = tmp_path / "edge.db"
    logger = _append_pick(str(csv_path))

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE sinais (
                id INTEGER,
                liga TEXT,
                jogo TEXT,
                resultado TEXT,
                odd REAL,
                prediction_id TEXT,
                horario TEXT,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            INSERT INTO sinais VALUES (
                1, 'Premier League', 'Arsenal vs Chelsea', 'verde', 1.92, 'pred-1',
                '2026-04-04T10:00:00+00:00', 'finalizado'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    logger.sync_from_db(str(db_path))


def test_flask_nao_sobe_debug_true_por_padrao():
    class _FlaskStub:
        def route(self, *args, **kwargs):
            def _decorator(fn):
                return fn
            return _decorator

    flask_stub = types.ModuleType("flask")
    flask_stub.Flask = lambda *args, **kwargs: _FlaskStub()
    flask_stub.jsonify = lambda *args, **kwargs: {"args": args, "kwargs": kwargs}
    flask_stub.render_template = lambda *args, **kwargs: ""
    flask_stub.request = types.SimpleNamespace(args={})
    with patch.dict(os.environ, {"FLASK_DEBUG": "0"}, clear=False):
        with patch.dict(sys.modules, {"flask": flask_stub}, clear=False):
            app_module = importlib.import_module("app")
            app_module = importlib.reload(app_module)
            assert app_module.FLASK_DEBUG_ENABLED is False
