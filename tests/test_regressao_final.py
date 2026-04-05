import ast
import asyncio
import importlib
import inspect
import sqlite3
import sys
import types
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

from services import alert_service, dispatch_service, settlement_service


def _set_package_attr(module_name, module_obj):
    parent_name, _, child_name = module_name.rpartition(".")
    if not parent_name:
        return
    parent = sys.modules.get(parent_name)
    if parent is None:
        return
    if module_obj is None:
        if hasattr(parent, child_name):
            delattr(parent, child_name)
    else:
        setattr(parent, child_name, module_obj)


def _import_sem_alterar_syspath(module_name, stubs=None):
    syspath_antes = list(sys.path)
    original_module = sys.modules.get(module_name)
    sys.modules.pop(module_name, None)
    backup_stubs = {}
    if stubs:
        for stub_name, stub_module in stubs.items():
            backup_stubs[stub_name] = sys.modules.get(stub_name)
            sys.modules[stub_name] = stub_module
            _set_package_attr(stub_name, stub_module)
    importlib.import_module(module_name)
    for stub_name in backup_stubs:
        if backup_stubs[stub_name] is None:
            sys.modules.pop(stub_name, None)
            _set_package_attr(stub_name, None)
        else:
            sys.modules[stub_name] = backup_stubs[stub_name]
            _set_package_attr(stub_name, backup_stubs[stub_name])
    if original_module is None:
        sys.modules.pop(module_name, None)
        _set_package_attr(module_name, None)
    else:
        sys.modules[module_name] = original_module
        _set_package_attr(module_name, original_module)
    assert sys.path == syspath_antes


def test_debug_fail_importa_sem_syspath():
    stub_coletar = types.ModuleType("data.coletar_odds")
    stub_coletar.coletar_odds = lambda: []
    stub_analisar = types.ModuleType("model.analisar_jogo")
    stub_analisar.analisar_jogo = lambda jogo: {"ok": True}

    _import_sem_alterar_syspath(
        "debug_fail",
        stubs={
            "data.coletar_odds": stub_coletar,
            "model.analisar_jogo": stub_analisar,
        },
    )


def test_testar_resultado_importa_sem_syspath():
    stub_vr = types.ModuleType("data.verificar_resultados")
    stub_vr.buscar_resultado_jogo = lambda *args, **kwargs: None

    _import_sem_alterar_syspath(
        "testar_resultado",
        stubs={"data.verificar_resultados": stub_vr},
    )


def test_picks_log_entrypoint_importa_sem_syspath():
    _import_sem_alterar_syspath("picks_log")


def test_data_verificar_resultados_importa_sem_syspath():
    _import_sem_alterar_syspath("data.verificar_resultados")


def test_data_sos_ajuste_importa_sem_syspath():
    _import_sem_alterar_syspath("data.sos_ajuste")


def test_logs_update_excel_importa_sem_syspath():
    _import_sem_alterar_syspath("logs.update_excel")


def test_test_model_analisar_jogo_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_model_analisar_jogo")


def test_test_scheduler_provider_health_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_scheduler_provider_health")


def test_test_settlement_fixture_resolution_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_settlement_fixture_resolution")


def test_test_clv_brier_picks_log_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_clv_brier_picks_log")


def test_test_bugs_p1_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_bugs_p1")


def test_test_poisson_over_under_dc_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_poisson_over_under_dc")


def test_test_filtros_gate_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_filtros_gate")


def test_test_advanced_pipeline_modules_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_advanced_pipeline_modules")


def test_test_picks_log_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_picks_log")


def test_test_calibrator_importa_sem_syspath():
    _import_sem_alterar_syspath("tests.test_calibrator")


def test_settlement_service_processa_resultado(tmp_path):
    db_path = tmp_path / "edge_protocol.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sinais (
            id INTEGER PRIMARY KEY,
            jogo TEXT,
            mercado TEXT,
            odd REAL,
            horario TEXT,
            fixture_id_api TEXT,
            fixture_data_api TEXT,
            liga TEXT,
            status TEXT,
            message_id_vip INTEGER,
            message_id_free INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sinais (id, jogo, mercado, odd, horario, fixture_id_api, fixture_data_api, liga, status, message_id_vip, message_id_free)
        VALUES (1, 'Arsenal vs Chelsea', '1x2_casa', 2.0, '2026-04-04T12:00:00Z', '9001', '2026-04-04', 'Premier League', 'pendente', 101, 202)
        """
    )
    conn.commit()
    conn.close()

    fake_vr = types.ModuleType("verificar_resultados")
    fake_vr.buscar_resultado_jogo = lambda *args, **kwargs: {
        "status": "finalizado",
        "fixture_id_api": "9001",
        "fixture_data_api": "2026-04-04",
        "gols_casa": 2,
        "gols_fora": 1,
    }
    fake_vr.avaliar_mercado = lambda *args, **kwargs: {"resultado": "verde", "lucro": 1.0}
    old_vr = sys.modules.get("verificar_resultados")
    sys.modules["verificar_resultados"] = fake_vr

    mock_update = MagicMock()
    mock_set_bank = MagicMock(return_value={"banca_atual": 1001.0})
    mock_brier = MagicMock(return_value=0.1)
    mock_estado = MagicMock(return_value={"banca_atual": 1001.0})
    mock_excel = MagicMock()
    mock_fix_ref = MagicMock()
    mock_clv = MagicMock()
    mock_shadow = MagicMock()
    mock_eval = MagicMock(return_value={"recommend_promote": False})
    mock_excel_full = MagicMock()
    mock_log_event = MagicMock()
    mock_degrade = MagicMock()

    context = {
        "TOKEN": "token",
        "CANAL_VIP": "vip",
        "CANAL_FREE": "free",
        "DB_PATH": str(db_path),
        "BOT_DATA_DIR": str(tmp_path),
        "MINIMAL_RUNTIME_OUTPUT": True,
        "MODEL_SHADOW_MODE": False,
        "MODEL_SHADOW_PROMOTION_WINDOW_DAYS": 21,
        "MODEL_SHADOW_BOOTSTRAP_ITERS": 2000,
        "LIGA_KEY_MAP": {"Premier League": "soccer_epl"},
        "log_event": mock_log_event,
        "marcar_ciclo_degradado": mock_degrade,
        "atualizar_resultado": mock_update,
        "atualizar_banca": mock_set_bank,
        "atualizar_brier": mock_brier,
        "carregar_estado_banca": mock_estado,
        "atualizar_excel": mock_excel,
        "atualizar_fixture_referencia": mock_fix_ref,
        "buscar_odd_fechamento_pinnacle": MagicMock(return_value=1.9),
        "atualizar_clv": mock_clv,
        "liquidar_shadow_predictions_por_sinal": mock_shadow,
        "evaluate_shadow_promotion": mock_eval,
        "gerar_excel": mock_excel_full,
    }

    try:
        with patch("services.settlement_service.Bot") as bot_cls:
            bot_instance = bot_cls.return_value
            bot_instance.set_message_reaction = AsyncMock(return_value=None)
            asyncio.run(settlement_service.processar_settlement(context))

        mock_update.assert_called_once_with(1, "verde", 1.0)
        assert mock_clv.called
    finally:
        if old_vr is None:
            sys.modules.pop("verificar_resultados", None)
        else:
            sys.modules["verificar_resultados"] = old_vr


def test_alert_service_emite_sem_runtime_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with patch("services.alert_service.Bot.send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            asyncio.run(alert_service.emitir("operacional", "teste", token="token", chat_id="vip"))
        assert not any(issubclass(x.category, RuntimeWarning) for x in w)


def test_alert_service_chama_bot_send_message():
    with patch("services.alert_service.Bot.send_message", new_callable=AsyncMock) as mock_send:
        asyncio.run(alert_service.emitir("operacional", "teste", token="token", chat_id="vip"))
        mock_send.assert_called_once()


def test_dispatch_formata_pick_sem_campos_nulos():
    pick = {
        "decisao": "PREMIUM",
        "liga": "Brasileirao",
        "jogo": "Flamengo vs Palmeiras",
        "mercado": "1x2_casa",
        "odd": 1.85,
        "edge_score": 82,
        "ev_percentual": "12%",
        "stake_reais": 25.0,
        "fonte_dados": "xG",
    }
    kelly = {"tier": "premium", "kelly_final_pct": 2.5}
    mensagem = dispatch_service.formatar_pick(pick, kelly, lambda: {"banca_atual": 1000.0})
    assert "Flamengo" in mensagem
    assert "None" not in mensagem


def test_dispatch_envia_resumo_diario():
    resumo = dispatch_service.formatar_resumo_diario(
        {
            "total": 5,
            "vitorias": 3,
            "derrotas": 2,
            "lucro": 1.2,
            "win_rate": 60,
            "banca": 1005.0,
            "roi": 2.0,
            "drawdown": 1.0,
        }
    )
    with patch("services.dispatch_service.Bot.send_message", new_callable=AsyncMock) as mock_send:
        asyncio.run(dispatch_service.enviar_resumo(resumo, token="token", canal_vip="vip", canal_free="free"))
        assert mock_send.call_count == 2


def test_scheduler_nao_tem_logica_de_settlement_inline():
    import scheduler

    source = inspect.getsource(scheduler)
    tree = ast.parse(source)
    funcoes = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "processar_settlement" not in funcoes
    assert "calcular_pl" not in funcoes
