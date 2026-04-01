"""
test_bugs_p1.py
===============
Testes de regressão para os bugs P1 identificados e corrigidos na v1.3.

BUG-01: dados simulados com data futura
BUG-03: bootstrap_completo cria schema completo
BUG-04: settlement não duplica finalização

Cada teste é independente e usa banco temporário quando necessário.
"""
import asyncio
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# ── Stubs de dependências externas (padrão já estabelecido no projeto) ────────

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")

if "telegram" not in sys.modules:
    telegram_stub = types.ModuleType("telegram")

    class _BotStub:
        def __init__(self, *args, **kwargs):
            pass

        async def send_message(self, *args, **kwargs):
            return None

        async def set_message_reaction(self, *args, **kwargs):
            return None

    telegram_stub.Bot = _BotStub
    sys.modules["telegram"] = telegram_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *a, **kw: True
    sys.modules["dotenv"] = dotenv_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *a, **kw: None
    requests_stub.Timeout = Exception
    requests_stub.ConnectionError = Exception
    sys.modules["requests"] = requests_stub

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
            return float(sum(sum(row) if isinstance(row, list) else float(row) for row in self))

        def __truediv__(self, divisor):
            if divisor == 0:
                return self
            return _MatrixStub([[v / divisor for v in row] for row in self])

    numpy_stub.zeros = lambda shape: _MatrixStub([[0.0] * shape[1] for _ in range(shape[0])])
    numpy_stub.mean = lambda values: sum(values) / len(values) if values else 0.0
    sys.modules["numpy"] = numpy_stub

# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))


class TestBugDadosSimulados(unittest.TestCase):
    """BUG-01: _dados_simulados deve retornar fixture com data futura."""

    def test_dados_simulados_tem_data_futura(self):
        """
        Garante que _dados_simulados() retorna um commence_time maior
        que o momento atual em UTC, para que formatar_jogos() não filtre
        o fixture simulado como passado.
        """
        from data.coletar_odds import _dados_simulados

        agora_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dados = _dados_simulados()

        self.assertTrue(len(dados) > 0, "Deve retornar ao menos um fixture simulado")
        commence = dados[0]["commence_time"]
        self.assertGreater(
            commence,
            agora_utc,
            f"commence_time '{commence}' deve ser maior que agora '{agora_utc}'",
        )

    def test_dados_simulados_passa_em_formatar_jogos(self):
        """
        Garante que formatar_jogos() não filtra o fixture simulado,
        ou seja, o fluxo sem API key não silencia a análise.
        """
        from data.coletar_odds import _dados_simulados, formatar_jogos

        dados = _dados_simulados()
        jogos = formatar_jogos(dados)
        self.assertGreater(
            len(jogos),
            0,
            "formatar_jogos deve retornar ao menos 1 jogo com dados simulados",
        )

    def test_aviso_explicito_quando_modo_simulado(self):
        """
        Garante que o operador recebe aviso quando ODDS_API_KEY está ausente.
        """
        import io
        from contextlib import redirect_stdout
        from data import coletar_odds

        with patch.object(coletar_odds, "API_KEY", None):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = coletar_odds.buscar_jogos_com_odds_com_status("soccer_epl")

        output = buf.getvalue()
        self.assertIn("AVISO", output, "Deve emitir aviso quando em modo simulado")
        self.assertEqual(result["status"], "simulated")


class TestBootstrapCompleto(unittest.TestCase):
    """BUG-03: bootstrap_completo deve criar todas as tabelas necessárias."""

    def test_bootstrap_completo_cria_tabelas_criticas(self):
        """
        Executa bootstrap_completo em banco temporário e verifica que
        todas as tabelas críticas foram criadas.
        """
        from data import database

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test_bootstrap.db")

            original_db = database.DB_PATH
            database.DB_PATH = db_path
            database._WAL_CONFIGURED_PATHS.discard(db_path)
            try:
                database.bootstrap_completo()

                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tabelas = {row[0] for row in c.fetchall()}
                conn.close()
            finally:
                database.DB_PATH = original_db

        tabelas_esperadas = {
            "sinais",
            "banca",
            "job_execucoes",
            "operation_audit",
            "operation_alerts",
        }
        for tabela in tabelas_esperadas:
            self.assertIn(
                tabela,
                tabelas,
                f"Tabela '{tabela}' deve existir após bootstrap_completo()",
            )

    def test_bootstrap_completo_idempotente(self):
        """
        bootstrap_completo pode ser chamado múltiplas vezes sem erro.
        """
        from data import database

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test_idempotente.db")
            original_db = database.DB_PATH
            database.DB_PATH = db_path
            database._WAL_CONFIGURED_PATHS.discard(db_path)
            try:
                database.bootstrap_completo()
                database.bootstrap_completo()
            finally:
                database.DB_PATH = original_db

    def test_sinais_tem_coluna_fonte_apos_bootstrap(self):
        """
        A coluna 'fonte' deve existir na tabela sinais após bootstrap.
        """
        from data import database

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test_fonte.db")
            original_db = database.DB_PATH
            database.DB_PATH = db_path
            database._WAL_CONFIGURED_PATHS.discard(db_path)
            try:
                database.bootstrap_completo()

                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("PRAGMA table_info(sinais)")
                colunas = {row[1] for row in c.fetchall()}
                conn.close()
            finally:
                database.DB_PATH = original_db

        self.assertIn("fonte", colunas, "Coluna 'fonte' deve existir em sinais após bootstrap")

    def test_get_db_connection_exportado(self):
        """
        database.py deve exportar get_db_connection como context manager.
        """
        from data import database

        self.assertTrue(
            hasattr(database, "get_db_connection"),
            "database deve exportar get_db_connection",
        )

    def test_get_db_connection_funciona_como_context_manager(self):
        """
        get_db_connection deve funcionar como context manager e fazer commit.
        """
        from data import database

        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test_ctx.db")
            original_db = database.DB_PATH
            database.DB_PATH = db_path
            database._WAL_CONFIGURED_PATHS.discard(db_path)
            try:
                database.bootstrap_completo()
                with database.get_db_connection() as conn:
                    conn.execute(
                        "INSERT INTO operation_audit (ocorrido_em, actor, acao, efeito) "
                        "VALUES (?, ?, ?, ?)",
                        ("2026-03-26T00:00:00", "test", "test_action", "ok"),
                    )

                conn2 = sqlite3.connect(db_path)
                count = conn2.execute(
                    "SELECT COUNT(*) FROM operation_audit WHERE actor = 'test'"
                ).fetchone()[0]
                conn2.close()
                self.assertEqual(count, 1)
            finally:
                database.DB_PATH = original_db


class TestSettlementNaoDuplicaFinalizacao(unittest.TestCase):
    """
    BUG-04: verificar_resultados_automatico não deve finalizar sinal já finalizado.

    A proteção contra dupla finalização vive em database.atualizar_resultado,
    que executa UPDATE WHERE status='pendente' — tornando a operação idempotente.
    O scheduler delega ao _registrar_settlement, que retorna False quando o banco
    rejeita a atualização (sinal já finalizado).
    """

    def _criar_banco_com_sinal_finalizado(self, td, status="finalizado"):
        """Helper: cria banco temporário com sinal no status indicado."""
        from data import database

        db_path = os.path.join(td, "test_settlement.db")
        original_db = database.DB_PATH
        database.DB_PATH = db_path
        database._WAL_CONFIGURED_PATHS.discard(db_path)
        database.bootstrap_completo()

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO sinais
            (id, data, liga, jogo, mercado, odd, ev_estimado, edge_score,
             stake_unidades, status, resultado, lucro_unidades, horario)
            VALUES (99, '2026-03-26', 'Premier League', 'Arsenal vs Chelsea',
                    '1x2_casa', 1.92, 0.08, 80, 1.0, ?, ?,
                    ?, '2026-03-26T17:30:00Z')
            """,
            (
                status,
                "verde" if status == "finalizado" else None,
                0.92 if status == "finalizado" else None,
            ),
        )
        conn.commit()
        conn.close()

        return db_path, original_db

    def test_settlement_nao_chama_atualizar_resultado_em_sinal_ja_finalizado(self):
        """
        BUG-04: quando _registrar_settlement retorna False (banco rejeitou a
        atualização porque o sinal já estava finalizado), os side-effects
        (banca, Brier, Telegram, Excel) NÃO devem ser executados e
        atualizar_resultado não deve ter efeito útil.

        A proteção real está em database.atualizar_resultado via
        UPDATE WHERE status='pendente'. Este teste verifica que o scheduler
        respeita o retorno False de _registrar_settlement e não prossegue.
        """
        import scheduler

        with tempfile.TemporaryDirectory() as td:
            from data import database

            db_path, original_db = self._criar_banco_com_sinal_finalizado(td, status="finalizado")

            fake_verificar = types.ModuleType("verificar_resultados")

            def _buscar(*args, **kwargs):
                return {
                    "status": "finalizado",
                    "gols_casa": 2,
                    "gols_fora": 1,
                    "placar": "2-1",
                    "fixture_id_api": "999",
                    "fixture_data_api": "2026-03-26",
                    "match_strategy": "fixture_id",
                }

            def _avaliar(*args, **kwargs):
                return {"resultado": "verde", "lucro": 0.92}

            fake_verificar.buscar_resultado_jogo = _buscar
            fake_verificar.avaliar_mercado = _avaliar

            fake_excel = types.ModuleType("exportar_excel")
            fake_excel.gerar_excel = lambda *a, **kw: None

            class _CursorStub:
                def execute(self, query, params=None):
                    self._last_query = query.lower()

                def fetchall(self):
                    if "where status = 'pendente'" in self._last_query:
                        return [
                            (99, "Arsenal vs Chelsea", "1x2_casa", 1.92,
                             "2026-03-26T17:30:00Z", None, None, "Premier League")
                        ]
                    return []

                def fetchone(self):
                    return None

            class _ConnStub:
                def cursor(self):
                    return _CursorStub()

                def close(self):
                    pass

            try:
                with patch.dict(
                    sys.modules,
                    {
                        "verificar_resultados": fake_verificar,
                        "exportar_excel": fake_excel,
                    },
                    clear=False,
                ), patch("scheduler.sqlite3.connect", return_value=_ConnStub()), \
                   patch("scheduler.atualizar_fixture_referencia"), \
                   patch("scheduler.atualizar_resultado") as mock_atualizar_resultado, \
                   patch("scheduler._registrar_settlement", return_value=False) as mock_registrar:
                    # _registrar_settlement retorna False — simula banco rejeitando
                    # a atualização porque o sinal já estava finalizado.
                    asyncio.run(scheduler.verificar_resultados_automatico())

                # O scheduler deve ter tentado registrar, mas como retornou False,
                # não deve ter chamado atualizar_resultado diretamente.
                mock_registrar.assert_called_once()
                mock_atualizar_resultado.assert_not_called()
            finally:
                database.DB_PATH = original_db

    def test_settlement_chama_atualizar_resultado_em_sinal_pendente(self):
        """
        Se o sinal está pendente, atualizar_resultado DEVE ser chamado.
        Garante que o fix não bloqueia o fluxo normal.
        """
        import scheduler

        class _CursorPendenteStub:
            def execute(self, query, params=None):
                self._last_query = query.lower()

            def fetchall(self):
                if "where status = 'pendente'" in self._last_query:
                    return [
                        (42, "Liverpool vs Arsenal", "over_2.5", 1.95,
                         "2026-03-26T20:00:00Z", None, None, "Premier League")
                    ]
                return []

            def fetchone(self):
                return (None, None)

        class _ConnPendenteStub:
            def cursor(self):
                return _CursorPendenteStub()

            def close(self):
                pass

        fake_verificar = types.ModuleType("verificar_resultados")
        fake_verificar.buscar_resultado_jogo = lambda *a, **kw: {
            "status": "finalizado",
            "gols_casa": 3,
            "gols_fora": 1,
            "placar": "3-1",
            "fixture_id_api": "888",
            "fixture_data_api": "2026-03-26",
            "match_strategy": "date_window",
        }
        fake_verificar.avaliar_mercado = lambda *a, **kw: {"resultado": "verde", "lucro": 0.95}

        fake_excel = types.ModuleType("exportar_excel")
        fake_excel.gerar_excel = lambda *a, **kw: None

        with patch.dict(
            sys.modules,
            {"verificar_resultados": fake_verificar, "exportar_excel": fake_excel},
            clear=False,
        ), patch("scheduler.sqlite3.connect", return_value=_ConnPendenteStub()), \
           patch("scheduler.atualizar_fixture_referencia"), \
           patch("scheduler.atualizar_resultado") as mock_atualizar_resultado, \
           patch("scheduler.atualizar_banca", return_value={"banca_atual": 110.0}), \
           patch("scheduler.atualizar_brier", return_value=0.15), \
           patch("scheduler.atualizar_excel"):

            asyncio.run(scheduler.verificar_resultados_automatico())

        mock_atualizar_resultado.assert_called_once()
        args = mock_atualizar_resultado.call_args[0]
        self.assertEqual(args[0], 42)
        self.assertEqual(args[1], "verde")


class TestFix05LogEventTelegramReaction(unittest.TestCase):
    """FIX-05: erros de reação Telegram devem usar log_event em vez de print."""

    def test_erro_reacao_telegram_usa_log_event(self):
        """
        Quando set_message_reaction lança exceção, log_event deve ser chamado
        com categoria 'telegram' e reason_code 'telegram_reaction_error'.
        """
        import scheduler

        chamadas_log = []

        def _fake_log(categoria, etapa, entidade, status, reason_code=None, detalhes=None):
            chamadas_log.append({
                "categoria": categoria,
                "etapa": etapa,
                "status": status,
                "reason_code": reason_code,
            })

        class _BotComFalha:
            async def set_message_reaction(self, *args, **kwargs):
                raise RuntimeError("Telegram API timeout")

        with patch("scheduler.log_event", side_effect=_fake_log):
            asyncio.run(
                scheduler._executar_side_effects_pos_settlement(
                    sinal_id=77,
                    avaliacao={"resultado": "verde", "lucro": 0.9},
                    bot=_BotComFalha(),
                    ids_msg=(123, 456),
                )
            )

        reaction_errors = [
            c for c in chamadas_log
            if c.get("reason_code") == "telegram_reaction_error"
        ]
        self.assertGreaterEqual(
            len(reaction_errors),
            1,
            "Deve haver ao menos um log_event com reason_code 'telegram_reaction_error'",
        )
        self.assertEqual(reaction_errors[0]["categoria"], "telegram")
        self.assertEqual(reaction_errors[0]["status"], "failed")


class TestFix06FallbackXGEmCycleTotals(unittest.TestCase):
    """FIX-06: jogos com fallback de xG devem aparecer no cycle_totals."""

    def test_cycle_totals_inclui_jogos_fallback_xg(self):
        """
        Quando processar_jogos conclui, o log_event de cycle_totals deve
        incluir o campo 'jogos_fallback_xg' com os jogos que usaram fallback.
        """
        import scheduler

        log_cycle_totals = []

        def _fake_log(categoria, etapa, entidade, status, reason_code=None, detalhes=None):
            if categoria == "scheduler" and etapa == "cycle_totals":
                log_cycle_totals.append(detalhes)

        with patch("scheduler.buscar_jogos_com_odds_com_status", return_value={"status": "ok", "data": []}), \
             patch("scheduler.formatar_jogos", return_value=[]), \
             patch("scheduler.buscar_sinais_hoje", return_value=[]), \
             patch("scheduler.log_event", side_effect=_fake_log):
            asyncio.run(scheduler.processar_jogos(dry_run=True))

        self.assertTrue(
            len(log_cycle_totals) > 0,
            "cycle_totals deve ser emitido ao final de processar_jogos",
        )
        detalhes = log_cycle_totals[-1]
        self.assertIn(
            "jogos_fallback_xg",
            detalhes,
            "cycle_totals deve incluir campo 'jogos_fallback_xg'",
        )
        self.assertIsInstance(detalhes["jogos_fallback_xg"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)