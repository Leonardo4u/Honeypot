import asyncio
import importlib
import sys
import types
import warnings
from unittest.mock import AsyncMock, patch


def _import_without_syspath(module_name: str, stub_modules: dict[str, types.ModuleType]):
    syspath_antes = sys.path.copy()
    sys.modules.pop(module_name, None)
    with patch.dict(sys.modules, stub_modules, clear=False):
        importlib.import_module(module_name)
    assert sys.path == syspath_antes


def test_criar_tabelas_importa_sem_syspath():
    stub_db = types.ModuleType("data.database")
    stub_db.criar_banco = lambda: None
    stub_db.bootstrap_completo = lambda: None

    stub_kelly = types.ModuleType("data.kelly_banca")
    stub_kelly.criar_tabela_banca = lambda: None

    stub_clv = types.ModuleType("data.clv_brier")
    stub_clv.criar_tabelas_validacao = lambda: None

    _import_without_syspath(
        "criar_tabelas",
        {
            "data.database": stub_db,
            "data.kelly_banca": stub_kelly,
            "data.clv_brier": stub_clv,
        },
    )


def test_debug_hoje_importa_sem_syspath():
    stub_coletar = types.ModuleType("data.coletar_odds")
    stub_coletar.buscar_jogos_com_odds = lambda *args, **kwargs: []
    stub_coletar.formatar_jogos = lambda dados: []

    stub_analisar = types.ModuleType("model.analisar_jogo")
    stub_analisar.analisar_jogo = lambda dados: {"ev_percentual": "0%", "edge_score": 0, "decisao": "DESCARTAR"}

    stub_stats = types.ModuleType("data.atualizar_stats")
    stub_stats.carregar_medias = lambda *args, **kwargs: {}

    stub_xg = types.ModuleType("data.xg_understat")
    stub_xg.calcular_media_gols_com_xg = lambda *args, **kwargs: (1.0, 1.0, "stub")

    stub_filtros = types.ModuleType("model.filtros")
    stub_filtros.aplicar_triple_gate = lambda *args, **kwargs: {"aprovado": True, "motivo": "ok"}

    _import_without_syspath(
        "debug_hoje",
        {
            "data.coletar_odds": stub_coletar,
            "model.analisar_jogo": stub_analisar,
            "data.atualizar_stats": stub_stats,
            "data.xg_understat": stub_xg,
            "model.filtros": stub_filtros,
        },
    )


def test_verificar_jogos_hoje_importa_sem_syspath():
    stub_coletar = types.ModuleType("data.coletar_odds")
    stub_coletar.buscar_jogos_com_odds = lambda *args, **kwargs: []
    stub_coletar.formatar_jogos = lambda dados: []

    _import_without_syspath(
        "verificar_jogos_hoje",
        {"data.coletar_odds": stub_coletar},
    )


def test_calibrate_importa_sem_syspath():
    _import_without_syspath("calibrate", {})


def test_dashboard_importa_sem_syspath():
    _import_without_syspath("dashboard", {})


def test_emitir_alerta_nao_gera_runtime_warning():
    import scheduler

    alerta = {"severidade": "warning", "codigo": "teste", "playbook": "PB-01", "detalhes": {}}
    bot = type("BotStub", (), {"send_message": AsyncMock(return_value=None)})()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with patch.object(scheduler, "TOKEN", "token"), \
             patch.object(scheduler, "CANAL_VIP", "123"), \
             patch("scheduler.Bot", return_value=bot), \
             patch("scheduler.registrar_alerta_operacional"), \
             patch("scheduler.log_event"):
            asyncio.run(scheduler.emitir_alerta_operacional(alerta))

    runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert len(runtime_warnings) == 0


def test_emitir_alerta_operacional_executa():
    import scheduler

    alerta = {"severidade": "warning", "codigo": "teste", "playbook": "PB-01", "detalhes": {}}
    with patch.object(scheduler, "TOKEN", "token"), \
         patch.object(scheduler, "CANAL_VIP", "123"), \
         patch("scheduler.registrar_alerta_operacional"), \
         patch("scheduler.log_event"), \
         patch("scheduler.Bot.send_message", new_callable=AsyncMock) as mock_send:
        asyncio.run(scheduler.emitir_alerta_operacional(alerta))

    mock_send.assert_called_once()
