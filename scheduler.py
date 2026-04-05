import logging
logging.basicConfig(
    filename='logs/scheduler_errors.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s'
)

import asyncio
import sys
import os
import math
import re
import json
import traceback
import schedule
import time
import sqlite3
import subprocess
import random
import json as _json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone

from model.analisar_jogo import analisar_jogo, formatar_sinal
from model.filtros import aplicar_triple_gate
from data.database import (
    DB_PATH,
    buscar_sinais_hoje,
    contar_sinais_duplicados_mesmo_dia,
    calcular_exposicao_pendente_unidades,
    calcular_perda_diaria_unidades,
    finalizar_execucao_job,
    garantir_schema_minimo,
    garantir_tabela_execucoes,
    obter_slo_disponibilidade_ciclo,
    iniciar_execucao_job,
    inserir_sinal,
    registrar_alerta_operacional,
    registrar_auditoria_acao,
    registrar_diagnostico_modelo,
    registrar_fallback_cycle_detail,
    listar_sinais_duplicados_mesmo_dia,
    listar_shadow_settled_por_janela,
    liquidar_shadow_predictions_por_sinal,
    registrar_shadow_prediction,
    validar_schema_minimo,
    # FIX-11: bootstrap_completo disponível para fresh setup
    bootstrap_completo,
    # FIX-10: atualizar_resultado no namespace do módulo para ser mockável em testes
    # via patch('scheduler.atualizar_resultado') nos testes existentes.
    atualizar_resultado,
    # FIX: atualizar_fixture_referencia no namespace do módulo para ser mockável
    # via patch('scheduler.atualizar_fixture_referencia') nos testes.
    atualizar_fixture_referencia,
)
from data.coletar_odds import (
    buscar_jogos_com_odds,
    buscar_jogos_com_odds_com_status,
    formatar_jogos,
    atualizar_contadores_provider_health,
)
from data.atualizar_stats import carregar_medias, atualizar_todas_ligas
from data.forma_recente import calcular_ajuste_forma, calcular_confianca_contexto
from data.xg_understat import calcular_media_gols_com_xg
from data.sos_ajuste import calcular_xg_com_sos
from data.clv_brier import registrar_aposta_clv, atualizar_brier, buscar_sinais_para_fechar, buscar_odd_fechamento_pinnacle, atualizar_clv
from data.kelly_banca import calcular_kelly, atualizar_banca, contar_sinais_abertos, contar_sinais_liga_hoje, contar_sinais_mesmo_jogo_abertos, gerar_relatorio_diario, imprimir_relatorio, carregar_estado_banca
from data.steam_monitor import buscar_odds_todas_casas, salvar_snapshot, buscar_snapshot_abertura, calcular_steam, calcular_bonus_edge_score, salvar_steam_evento, gerar_alerta_steam
from data.janela_monitoramento import buscar_jogos_janela_expandida, registrar_jogo_monitorado, atualizar_modo_jogos, buscar_jogos_observacao, marcar_notificado, LIGAS_COPA, LIGAS_FIM_DE_SEMANA
from data.quality_telemetry import registrar_snapshot_qualidade_semanal, avaliar_drift_historico
from model.signal_policy import MIN_EDGE_SCORE, MIN_CONFIANCA
from model.edge_score import MIN_CONFIDENCE_ACTIONABLE
try:
    from model.signal_policy_v2 import (
        EVMinimoPolicy,
        SteamGatePolicy,
        gate_ev_steam,
        policy_v2_blocks,
        log_policy_v2_rejection,
    )
except Exception:
    EVMinimoPolicy = None
    SteamGatePolicy = None
    gate_ev_steam = None
    policy_v2_blocks = None
    log_policy_v2_rejection = None
from model.runtime_gate_context import inferir_escalacao_confirmada, calcular_variacao_odd_gate, calcular_sinais_hoje_gate
from model.module_01_sharp_money import MarketLine, OddsSnapshot, SharpMoneyDetector
from model.pipeline_integrador import BettingPipeline
from services.scheduler_services import (
    DataCollectionService,
    FallbackEvaluationService,
    ObservabilityService,
    DispatchSettlementService,
)
from services import alert_service, dispatch_service, settlement_service

from dotenv import load_dotenv
from telegram import Bot

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CANAL_VIP = os.getenv("CANAL_VIP")
CANAL_FREE = os.getenv("CANAL_FREE")
LOG_LEVEL = os.getenv("EDGE_LOG_LEVEL", "normal").strip().lower()
OPERATOR_ID = os.getenv("EDGE_OPERATOR", "system")
EDGE_VERSION = os.getenv("EDGE_VERSION", "dev")
MINIMAL_RUNTIME_OUTPUT = os.getenv("EDGE_MINIMAL_OUTPUT", "1").strip().lower() in ("1", "true", "yes", "on")
SHOW_STARTUP_BANNER = os.getenv("EDGE_SHOW_STARTUP_BANNER", "1").strip().lower() in ("1", "true", "yes", "on")
FORCE_ANSI_COLOR = os.getenv("EDGE_FORCE_ANSI_COLOR", "0").strip().lower() in ("1", "true", "yes", "on")
IDLE_ASCII_ANIM = os.getenv("EDGE_IDLE_ASCII_ANIM", "0").strip().lower() in ("1", "true", "yes", "on")
IDLE_ASCII_FRAME_MS = int(os.getenv("EDGE_IDLE_ASCII_FRAME_MS", "120"))
IDLE_ASCII_MAX_W = int(os.getenv("EDGE_IDLE_ASCII_MAX_W", "52"))
IDLE_ASCII_MAX_H = int(os.getenv("EDGE_IDLE_ASCII_MAX_H", "18"))

_DB_SCHEMA_READY = False


def _enable_windows_ansi():
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        if handle == 0:
            return False
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(handle, new_mode) == 0:
            return False
        return True
    except Exception:
        return False


_ANSI_ENABLED = FORCE_ANSI_COLOR or (sys.stdout.isatty() and _enable_windows_ansi())
MAGENTA = "\x1b[95m" if _ANSI_ENABLED else ""
ANSI_RESET = "\x1b[0m" if _ANSI_ENABLED else ""

_IDLE_ASCII_FRAMES = None

JOB_LABELS = {
    "analise": "analise de sinais",
    "janela_expandida": "monitoramento da janela expandida",
    "verificacao": "verificacao de resultados",
    "resumo": "resumo diario",
    "clv": "monitoramento CLV",
    "steam": "monitoramento steam",
}

MAX_SINAIS_DIA = int(os.getenv("EDGE_MAX_SINAIS_DIA", "10"))
MAX_MERCADOS_POR_JOGO = 2
CORRELACAO_PENALTY_STEP = 2.0
DRIFT_MIN_FALLBACK_LIMIAR = 0.35
DRIFT_HISTORICO_MIN_PERSISTENCIA = 3
DRIFT_HISTORICO_JANELA = 4
KILL_SWITCH = os.getenv("EDGE_KILL_SWITCH", "0").strip().lower() in ("1", "true", "yes", "on")
MAX_DAILY_LOSS_UNITS = float(os.getenv("EDGE_MAX_DAILY_LOSS_UNITS", "8.0"))
MAX_EXPOSURE_WINDOW_UNITS = float(os.getenv("EDGE_MAX_EXPOSURE_WINDOW_UNITS", "12.0"))
EXPOSURE_WINDOW_HOURS = int(os.getenv("EDGE_EXPOSURE_WINDOW_HOURS", "6"))
PROVIDER_ERROR_RATE_MAX = float(os.getenv("EDGE_PROVIDER_ERROR_RATE_MAX", "0.55"))
SLO_CYCLE_AVAILABILITY_MIN = float(os.getenv("SLO_CYCLE_AVAILABILITY_MIN", "0.95"))
SLO_FALLBACK_RATE_MAX = float(os.getenv("SLO_FALLBACK_RATE_MAX", "0.35"))
SLO_CYCLE_LATENCY_MAX_SECONDS = float(os.getenv("SLO_CYCLE_LATENCY_MAX_SECONDS", "120"))
SLO_DRIFT_MAX_BRIER = float(os.getenv("SLO_DRIFT_MAX_BRIER", "0.25"))
CANARY_RATIO = float(os.getenv("EDGE_CANARY_RATIO", "1.0"))
CANARY_MODE_ENABLED = os.getenv("EDGE_CANARY_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
QUALITY_CANARY_MIN_EDGE = 0.75
QUALITY_CANARY_MIN_SCORE = 82.0
QUALITY_CANARY_STAKE_FRACTION = 0.01
ANALISE_JOGO_TIMEOUT_SEGUNDOS = int(os.getenv("ANALISE_JOGO_TIMEOUT", "30"))
CICLO_TIMEOUT_SEGUNDOS = int(os.getenv("CICLO_TIMEOUT", "110"))
ADVANCED_PIPELINE_ENABLED = os.getenv("EDGE_ADVANCED_PIPELINE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
ADVANCED_PIPELINE_MC_SIMS = int(os.getenv("EDGE_ADVANCED_PIPELINE_MC_SIMS", "2000"))
PLAYBOOK_LINK = os.getenv("EDGE_PLAYBOOK_URL", "docs/runbooks/emergency.md")
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "logs", "update_excel.py")
BASE_DIR = os.path.dirname(__file__)
BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(BASE_DIR, "data"))
POLICY_V2_ENABLED = os.getenv("EDGE_POLICY_V2_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
POLICY_V2_SHADOW_MODE = os.getenv("EDGE_POLICY_V2_SHADOW", "1").strip().lower() in ("1", "true", "yes", "on")
MODEL_SHADOW_MODE = os.getenv("EDGE_MODEL_SHADOW_MODE", "1").strip().lower() in ("1", "true", "yes", "on")
MODEL_SHADOW_PROMOTION_WINDOW_DAYS = int(os.getenv("EDGE_MODEL_SHADOW_WINDOW_DAYS", "21"))
MODEL_SHADOW_BOOTSTRAP_ITERS = int(os.getenv("EDGE_MODEL_SHADOW_BOOTSTRAP_ITERS", "2000"))
MIN_CONFIANCA_EFETIVA = max(float(MIN_CONFIANCA), float(MIN_CONFIDENCE_ACTIONABLE))
DRY_RUN_RELAXED_GATES = os.getenv("EDGE_DRY_RUN_RELAXED_GATES", "0").strip().lower() in ("1", "true", "yes", "on")

EXECUCAO_CICLO = {
    "job_nome": None,
    "janela_chave": None,
    "status": "ok",
    "reason_codes": [],
}

EXECUCAO_STATS = {
    "duracao_segundos": 0.0,
    "provider_health": {},
    "total_avaliacoes_mercado": 0,
}

# Arquitetura proposta (fase 6): scheduler como composição de serviços.
# - DataCollectionService: coleta e normalização de jogos por liga.
# - FallbackEvaluationService: avaliação e persistência de fallback detalhado.
# - ObservabilityService: padronização de warning estruturado com contexto operacional.
# - DispatchSettlementService: composição do envio/persistência de sinais no runtime.
DATA_COLLECTION_SERVICE = DataCollectionService(
    fetcher=buscar_jogos_com_odds_com_status,
    formatter=formatar_jogos,
    health_counter=atualizar_contadores_provider_health,
)
OBSERVABILITY_SERVICE = None
FALLBACK_SERVICE = None
DISPATCH_SERVICE = None

ADVANCED_PIPELINE = None
ADVANCED_SHARP = SharpMoneyDetector()
EV_POLICY_V2 = EVMinimoPolicy(execucao_automatizada=True) if EVMinimoPolicy is not None else None
STEAM_POLICY_V2 = SteamGatePolicy() if SteamGatePolicy is not None else None
if ADVANCED_PIPELINE_ENABLED:
    try:
        ADVANCED_PIPELINE = BettingPipeline(
            mc_simulations=ADVANCED_PIPELINE_MC_SIMS,
            alert_hook=lambda severidade, codigo, detalhes=None: registrar_alerta_operacional(
                severidade,
                codigo,
                playbook_id="advanced_pipeline_fallback",
                detalhes=detalhes,
            ),
        )
    except Exception:
        ADVANCED_PIPELINE = None

LIGAS = [
    "soccer_epl",
    "soccer_brazil_campeonato",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one"
]

MARKET_RUNTIME_CONFIG = [
    {"mercado": "1x2_casa", "odd_key": "casa", "odd_oponente_key": "fora"},
    {"mercado": "1x2_fora", "odd_key": "fora", "odd_oponente_key": "casa"},
    {"mercado": "over_2.5", "odd_key": "over_2.5", "odd_oponente_key": "under_2.5"},
    {"mercado": "under_2.5", "odd_key": "under_2.5", "odd_oponente_key": "over_2.5"},
]

LIGA_KEY_MAP = {
    "EPL": "soccer_epl",
    "Premier League": "soccer_epl",
    "Brazil Série A": "soccer_brazil_campeonato",
    "Brasileirao Serie A": "soccer_brazil_campeonato",
    "UEFA Champions League": "soccer_uefa_champs_league",
    "UEFA Europa League": "soccer_uefa_europa_league",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one"
}

def log_event(categoria, etapa, entidade, status, reason_code=None, detalhes=None):
    if MINIMAL_RUNTIME_OUTPUT:
        if categoria == "scheduler" and etapa == "job_guard" and status == "start":
            label = JOB_LABELS.get(entidade, entidade)
            logging.info("%s...", label)
            return

        if categoria == "scheduler" and etapa == "job_guard" and status == "end":
            label = JOB_LABELS.get(entidade, entidade)
            logging.info("%s -> OK", label)
            return

        if categoria == "scheduler" and etapa == "cycle_totals":
            enviados = 0
            if isinstance(detalhes, dict):
                enviados = int(detalhes.get("enviados", 0) or 0)
            logging.info("enviado %s sinais", enviados)
            return

        if status in ("failed", "critical"):
            erro = None
            if isinstance(detalhes, dict):
                erro = detalhes.get("erro")
            if (
                reason_code == "PB-02"
                and entidade in ("slo_fallback_rate_breach", "provider_error_rate_high")
            ):
                logging.warning("-> ALERT PB-02: %s", entidade)
                logging.error("ALERT PB-02 em analise: %s", entidade)
                return
            motivo = str(erro or reason_code or "runtime_failure")
            logging.error("-> FAIL: %s", motivo)
            logging.error("FAIL em analise: %s", motivo)
            return

        return

    ts = datetime.now().strftime("%H:%M:%S")
    header = f"[{ts}] {categoria}/{etapa} {entidade} -> {status}"

    if reason_code:
        header += f" | reason={reason_code}"

    if LOG_LEVEL == "normal" and isinstance(detalhes, dict) and not reason_code:
        resumo = {}
        for k in ("enviados", "candidatos", "status_final", "janela_chave"):
            if k in detalhes:
                resumo[k] = detalhes[k]

        if resumo:
            resumo_txt = _json.dumps(resumo, ensure_ascii=False, separators=(",", ":"))
            print(f"{header} | resumo={resumo_txt}")
            return

        print(header)
        return

    if detalhes:
        detalhes_txt = _json.dumps(detalhes, ensure_ascii=False, separators=(",", ":"))
        print(f"{header} | detalhes={detalhes_txt}")
        return

    print(header)


OBSERVABILITY_SERVICE = ObservabilityService(log_event)
FALLBACK_SERVICE = FallbackEvaluationService(
    registrar_fallback_cycle_detail=registrar_fallback_cycle_detail,
    observability=OBSERVABILITY_SERVICE,
)
DISPATCH_SERVICE = DispatchSettlementService()


def _compactar_frame_ascii(frame, max_w, max_h):
    linhas = frame.splitlines()
    if not linhas:
        return ""

    while linhas and not linhas[0].strip():
        linhas.pop(0)
    while linhas and not linhas[-1].strip():
        linhas.pop()
    if not linhas:
        return ""

    min_col = None
    max_col = -1
    for linha in linhas:
        for idx, ch in enumerate(linha):
            if ch != " ":
                if min_col is None or idx < min_col:
                    min_col = idx
                if idx > max_col:
                    max_col = idx

    if min_col is None:
        return ""

    largura_real = (max_col - min_col) + 1
    altura_real = len(linhas)
    step_h = max(1, math.ceil(altura_real / max(1, max_h)))
    step_w = max(1, math.ceil(largura_real / max(1, max_w)))

    saida = []
    for linha in linhas[::step_h]:
        recorte = linha[min_col:max_col + 1]
        reduzida = recorte[::step_w].rstrip()
        if reduzida:
            saida.append(reduzida)

    if not saida:
        return ""

    return "\n".join(saida[:max_h])


def _normalizar_frames_idle(frames, max_w, max_h):
    if not frames:
        return []

    parsed = [f.splitlines() for f in frames if f.strip()]
    if not parsed:
        return []

    altura = min(max(len(linhas) for linhas in parsed), max(1, max_h))
    largura = min(
        max((len(linha) for linhas in parsed for linha in linhas), default=0),
        max(1, max_w),
    )
    if largura <= 0:
        return []

    normalizados = []
    for linhas in parsed:
        saida = []
        for linha in linhas[:altura]:
            recorte = linha[:largura]
            saida.append(recorte.ljust(largura))
        while len(saida) < altura:
            saida.append(" " * largura)
        normalizados.append("\n".join(saida))

    return normalizados


def _carregar_frames_idle():
    global _IDLE_ASCII_FRAMES
    if _IDLE_ASCII_FRAMES is not None:
        return _IDLE_ASCII_FRAMES

    path = os.path.join(BASE_DIR, "ascii_frames_all.txt")
    if not os.path.isfile(path):
        _IDLE_ASCII_FRAMES = []
        return _IDLE_ASCII_FRAMES

    try:
        conteudo = ""
        with open(path, "r", encoding="utf-8") as f:
            conteudo = f.read()

        partes = re.split(r"^===== FRAME \d+ =====\s*$", conteudo, flags=re.MULTILINE)
        frames_brutos = [p for p in partes if p.strip()]
        frames = []
        for bruto in frames_brutos:
            compacto = _compactar_frame_ascii(bruto, IDLE_ASCII_MAX_W, IDLE_ASCII_MAX_H)
            if compacto:
                frames.append(compacto)

        _IDLE_ASCII_FRAMES = _normalizar_frames_idle(frames, IDLE_ASCII_MAX_W, IDLE_ASCII_MAX_H)
        return _IDLE_ASCII_FRAMES
    except Exception:
        _IDLE_ASCII_FRAMES = []
        return _IDLE_ASCII_FRAMES


def _esperar_ocioso_com_animacao(segundos):
    if segundos <= 0:
        return

    if os.environ.get('EDGE_IDLE_ASCII_ANIM', 'true').lower() == 'false':
        time.sleep(segundos)
        return

    if not IDLE_ASCII_ANIM:
        time.sleep(segundos)
        return

    if not _ANSI_ENABLED:
        time.sleep(segundos)
        return

    frames = _carregar_frames_idle()
    if not frames:
        time.sleep(segundos)
        return

    atraso = max(0.05, IDLE_ASCII_FRAME_MS / 1000.0)
    fim = time.time() + segundos
    idx = 0
    linhas_prev = 0

    while True:
        restante = fim - time.time()
        if restante <= 0:
            break

        frame = frames[idx % len(frames)]
        linhas = frame.splitlines()
        if not linhas:
            linhas = [""]
        linhas_frame = len(linhas)

        if linhas_prev:
            sys.stdout.write(f"\x1b[{linhas_prev}F")

        for linha in linhas:
            sys.stdout.write("\x1b[2K" + MAGENTA + linha + ANSI_RESET + "\n")
        sys.stdout.flush()

        linhas_prev = linhas_frame
        idx += 1
        time.sleep(min(atraso, restante))

    if linhas_prev:
        sys.stdout.write(f"\x1b[{linhas_prev}F")
        for _ in range(linhas_prev):
            sys.stdout.write("\x1b[2K\n")
        sys.stdout.write(f"\x1b[{linhas_prev}F")
        sys.stdout.flush()


def resetar_execucao_ciclo(job_nome):
    EXECUCAO_CICLO["job_nome"] = job_nome
    EXECUCAO_CICLO["janela_chave"] = None
    EXECUCAO_CICLO["status"] = "ok"
    EXECUCAO_CICLO["reason_codes"] = []
    EXECUCAO_STATS["duracao_segundos"] = 0.0
    EXECUCAO_STATS["provider_health"] = {}
    EXECUCAO_STATS["total_avaliacoes_mercado"] = 0


def registrar_fallback_stats_medias(jogo, mercado, fonte_dados, source_quality):
    FALLBACK_SERVICE.persist_fallback_detail(
        job_nome=EXECUCAO_CICLO.get("job_nome"),
        janela_chave=EXECUCAO_CICLO.get("janela_chave"),
        liga=jogo.get("liga"),
        jogo=jogo.get("jogo"),
        mercado=mercado,
        motivo_fallback="fallback_stats_medias",
        detalhes={
            "fonte_dados": fonte_dados,
            "source_quality": source_quality,
        },
    )


def registrar_fallback_source_quality_low(jogo, mercado, fonte_dados, source_quality):
    FALLBACK_SERVICE.persist_fallback_detail(
        job_nome=EXECUCAO_CICLO.get("job_nome"),
        janela_chave=EXECUCAO_CICLO.get("janela_chave"),
        liga=jogo.get("liga"),
        jogo=jogo.get("jogo"),
        mercado=mercado,
        motivo_fallback="source_quality_low",
        detalhes={
            "fonte_dados": fonte_dados,
            "source_quality": source_quality,
        },
    )


def marcar_ciclo_degradado(reason_code, detalhes=None):
    if EXECUCAO_CICLO["status"] == "failed":
        return
    EXECUCAO_CICLO["status"] = 'degraded'
    if reason_code not in EXECUCAO_CICLO["reason_codes"]:
        EXECUCAO_CICLO["reason_codes"].append(reason_code)
    log_event("runtime", "cycle", EXECUCAO_CICLO.get("job_nome", "desconhecido"), "degraded", reason_code, detalhes)


def marcar_ciclo_falha(reason_code, detalhes=None):
    EXECUCAO_CICLO["status"] = "failed"
    if reason_code not in EXECUCAO_CICLO["reason_codes"]:
        EXECUCAO_CICLO["reason_codes"].append(reason_code)
    log_event("runtime", "cycle", EXECUCAO_CICLO.get("job_nome", "desconhecido"), "failed", reason_code, detalhes)


def _garantir_schema_db():
    """Garante schema mínimo do SQLite para ambientes fresh (ex.: CI)."""
    global _DB_SCHEMA_READY
    if _DB_SCHEMA_READY:
        return True
    try:
        bootstrap_completo()
        _DB_SCHEMA_READY = True
        return True
    except Exception as exc:
        log_event(
            "runtime",
            "db",
            "bootstrap",
            "critical",
            "db_schema_bootstrap_failed",
            {"erro": str(exc)},
        )
        return False


def _split_match_name(match_name):
    raw = str(match_name or "").strip()
    if " vs " in raw:
        home, away = raw.split(" vs ", 1)
        return home.strip(), away.strip()
    return raw, ""


def _duplicates_skipped_log_path():
    logs_dir = os.path.join(os.path.dirname(BOT_DATA_DIR), "logs")
    return logs_dir, os.path.join(logs_dir, "duplicates_skipped.log")


def _registrar_duplicate_skip(league, team_home, team_away, market):
    logs_dir, log_path = _duplicates_skipped_log_path()
    os.makedirs(logs_dir, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "league": str(league or ""),
        "team_home": str(team_home or ""),
        "team_away": str(team_away or ""),
        "market": str(market or ""),
        "reason": "duplicate_same_day",
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(payload, ensure_ascii=False) + "\n")


def construir_janela_chave(job_nome, bucket_minutes):
    agora = datetime.now()
    if bucket_minutes >= 60:
        bucket_horas = max(1, bucket_minutes // 60)
        hora_bucket = (agora.hour // bucket_horas) * bucket_horas
        return f"{agora.strftime('%Y%m%d')}-{job_nome}-h{hora_bucket:02d}"

    minuto_bucket = (agora.minute // bucket_minutes) * bucket_minutes
    return f"{agora.strftime('%Y%m%d-%H')}-{job_nome}-m{minuto_bucket:02d}"


def executar_job_guardado(job_nome, bucket_minutes, executor, force_once=False):
    janela_base = construir_janela_chave(job_nome, bucket_minutes)
    janela_chave = janela_base

    if force_once:
        janela_chave = f"{janela_base}-boot-{datetime.now().strftime('%H%M%S')}"

    inicio = iniciar_execucao_job(job_nome, janela_chave)

    if not inicio.get("iniciado"):
        log_event(
            "scheduler",
            "job_guard",
            job_nome,
            "skip",
            "idempotent_skip",
            {"janela_chave": janela_chave},
        )
        return

    resetar_execucao_ciclo(job_nome)
    EXECUCAO_CICLO["janela_chave"] = janela_chave
    log_event("scheduler", "job_guard", job_nome, "start", None, {"janela_chave": janela_chave})
    inicio_execucao = time.perf_counter()

    try:
        executor()
    except Exception as e:
        marcar_ciclo_falha("job_exception", {"erro": str(e), "janela_chave": janela_chave})
    finally:
        EXECUCAO_STATS["duracao_segundos"] = round(time.perf_counter() - inicio_execucao, 4)
        status_final = EXECUCAO_CICLO["status"]
        reason_code_final = EXECUCAO_CICLO["reason_codes"][0] if EXECUCAO_CICLO["reason_codes"] else None
        finalizar_execucao_job(
            job_nome,
            janela_chave,
            status_final,
            reason_code=reason_code_final,
            detalhes_json={
                "reason_codes": EXECUCAO_CICLO["reason_codes"],
                "duracao_segundos": EXECUCAO_STATS["duracao_segundos"],
                "provider_health": EXECUCAO_STATS.get("provider_health", {}),
                "total_avaliacoes_mercado": EXECUCAO_STATS.get("total_avaliacoes_mercado", 0),
            },
        )
        registrar_auditoria_acao(
            actor=OPERATOR_ID,
            acao=f"job:{job_nome}",
            efeito=status_final,
            detalhes={
                "janela_chave": janela_chave,
                "reason_code": reason_code_final,
                "duracao_segundos": EXECUCAO_STATS["duracao_segundos"],
            },
        )
        log_event(
            "scheduler",
            "job_guard",
            job_nome,
            "end",
            reason_code_final,
            {"janela_chave": janela_chave, "status_final": status_final},
        )


def validar_entrada_analise(jogo, odd):
    required_fields = ["home_team", "away_team", "jogo", "liga", "horario"]
    for field in required_fields:
        if not jogo.get(field):
            return False, "invalid_input_missing_field"

    try:
        odd_val = float(odd)
    except (TypeError, ValueError):
        return False, "invalid_input_odd"

    if odd_val <= 1.0:
        return False, "invalid_input_odd"

    return True, "ok"


def listar_mercados_runtime():
    return list(MARKET_RUNTIME_CONFIG)


def mapear_mercado_policy_v2(mercado):
    mapping = {
        "1x2_casa": "home_win",
        "1x2_fora": "away_win",
        "over_2.5": "over_2.5",
        "under_2.5": "under_2.5",
    }
    return mapping.get(mercado, mercado)


def minutos_ate_jogo(horario):
    try:
        kickoff = datetime.strptime(horario, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        delta = (kickoff - datetime.now(timezone.utc)).total_seconds() / 60.0
        return max(0.0, delta)
    except Exception:
        return 180.0


def aplicar_cap_por_jogo(candidatos, max_por_jogo=MAX_MERCADOS_POR_JOGO):
    selecionados = []
    por_jogo = {}
    for candidato in candidatos:
        jogo = candidato.get("jogo", {}).get("jogo")
        if not jogo:
            continue
        atual = por_jogo.get(jogo, 0)
        if atual >= max_por_jogo:
            continue
        por_jogo[jogo] = atual + 1
        selecionados.append(candidato)
    return selecionados


def aplicar_penalizacao_correlacao_ranking(candidatos, penalty_step=CORRELACAO_PENALTY_STEP):
    ordenados_base = sorted(
        candidatos,
        key=lambda x: (
            x.get("score_prior", x.get("score", 0)),
            x.get("score", 0),
            x.get("confianca", 0),
        ),
        reverse=True,
    )

    vistos_por_jogo = {}
    ajustados = []
    for candidato in ordenados_base:
        jogo = candidato.get("jogo", {}).get("jogo")
        contagem = vistos_por_jogo.get(jogo, 0)
        penalizacao = contagem * float(penalty_step)
        base = candidato.get("score_prior", candidato.get("score", 0))
        candidato["penalizacao_correlacao_ranking"] = round(penalizacao, 4)
        candidato["score_prior_ajustado"] = round(base - penalizacao, 4)
        vistos_por_jogo[jogo] = contagem + 1
        ajustados.append(candidato)

    return sorted(
        ajustados,
        key=lambda x: (
            x.get("score_prior_ajustado", x.get("score_prior", x.get("score", 0))),
            x.get("score_prior", x.get("score", 0)),
            x.get("score", 0),
            x.get("confianca", 0),
        ),
        reverse=True,
    )


def avaliar_alerta_drift_minimo(provider_health, total_avaliacoes, limiar=DRIFT_MIN_FALLBACK_LIMIAR):
    if total_avaliacoes <= 0:
        return None

    fallback_count = provider_health.get("fallback_used", 0)
    taxa_fallback = fallback_count / float(total_avaliacoes)
    if taxa_fallback >= limiar:
        return {
            "alerta": True,
            "metrica": "fallback_rate",
            "valor": round(taxa_fallback, 4),
            "limiar": limiar,
        }
    return None


def calcular_provider_error_rate(provider_health):
    total = sum(
        int(provider_health.get(k, 0))
        for k in ("ok", "timeout", "http_error", "connection_error", "empty_payload", "unknown_error")
    )
    if total <= 0:
        return 0.0
    erros = (
        int(provider_health.get("timeout", 0))
        + int(provider_health.get("http_error", 0))
        + int(provider_health.get("connection_error", 0))
        + int(provider_health.get("unknown_error", 0))
    )
    return round(erros / float(total), 4)


def aplicar_canary_operacional(selecionados, ratio=1.0, enabled=False):
    if not enabled:
        return selecionados, []

    ratio_num = max(0.0, min(1.0, float(ratio or 0.0)))
    if ratio_num >= 1.0:
        return selecionados, []

    permitidos = int(math.ceil(len(selecionados) * ratio_num))
    permitidos = max(0, min(len(selecionados), permitidos))
    return selecionados[:permitidos], selecionados[permitidos:]


def _quality_canary_enabled():
    return os.getenv("EDGE_QUALITY_CANARY_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _is_quality_canary_candidate(source_quality_low, edge, score):
    if not _quality_canary_enabled():
        return False
    try:
        edge_v = float(edge or 0.0)
        score_v = float(score or 0.0)
    except (TypeError, ValueError):
        return False
    return bool(source_quality_low) and edge_v >= QUALITY_CANARY_MIN_EDGE and score_v >= QUALITY_CANARY_MIN_SCORE


def _apply_quality_canary_stake_override(kelly_payload):
    banca = kelly_payload.get("banca_atual")
    if banca is None:
        banca = carregar_estado_banca().get("banca_atual", 0.0)
    try:
        banca_num = float(banca)
    except (TypeError, ValueError):
        banca_num = 0.0

    stake_pct = QUALITY_CANARY_STAKE_FRACTION * 100.0
    stake_reais = round(max(0.0, banca_num * QUALITY_CANARY_STAKE_FRACTION), 2)
    return round(stake_pct, 2), stake_reais


def _emit_quality_canary_log(edge, score):
    mensagem = f"[CANARY] source_quality_low bypass: edge={float(edge or 0.0):.2%} score={float(score or 0.0):.1f} stake=1%"
    logging.info(mensagem)
    print(mensagem)
    return mensagem


def _ler_timeout_env(var_name, fallback):
    try:
        return max(1, int(os.getenv(var_name, str(fallback))))
    except (TypeError, ValueError):
        return int(fallback)


def _timeout_analise_jogo_segundos():
    return _ler_timeout_env("ANALISE_JOGO_TIMEOUT", ANALISE_JOGO_TIMEOUT_SEGUNDOS)


def _timeout_ciclo_segundos():
    return _ler_timeout_env("CICLO_TIMEOUT", CICLO_TIMEOUT_SEGUNDOS)


def analisar_jogo_com_timeout(
    dados_analise,
    *,
    jogo,
    mercado,
    log_dc=True,
    timeout=None,
    analisar_fn=None,
    registrar_alerta_fn=None,
):
    timeout_segundos = int(timeout if timeout is not None else _timeout_analise_jogo_segundos())
    if analisar_fn is None:
        analisar_fn = analisar_jogo
    if registrar_alerta_fn is None:
        registrar_alerta_fn = registrar_alerta_operacional
    jogo_nome = str(jogo.get("jogo", dados_analise.get("jogo", "jogo_desconhecido")))
    home = str(jogo.get("home_team", ""))
    away = str(jogo.get("away_team", ""))
    confronto = f"{home} vs {away}" if home and away else jogo_nome

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(analisar_fn, dados_analise, log_dc=log_dc)
    try:
        return future.result(timeout=timeout_segundos)
    except FuturesTimeout:
        mensagem = (
            f"[WATCHDOG] Timeout de {timeout_segundos}s ao analisar "
            f"{confronto} ({mercado}) - jogo pulado"
        )
        print(mensagem)
        logging.error(mensagem)
        if registrar_alerta_fn is not None:
            registrar_alerta_fn(
                severidade="warning",
                codigo="watchdog_timeout",
                playbook_id="PB-03",
                detalhes={
                    "evento": "watchdog_timeout",
                    "jogo": confronto,
                    "mercado": mercado,
                    "timeout_segundos": timeout_segundos,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        return None
    except Exception as exc:
        mensagem = f"[WATCHDOG] Erro ao analisar jogo {confronto} ({mercado}): {exc}"
        print(mensagem)
        logging.error(mensagem)
        return None
    finally:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)


def avaliar_guardrails_hard_limits():
    perda_diaria = calcular_perda_diaria_unidades()
    exposicao_pendente = calcular_exposicao_pendente_unidades(janela_horas=EXPOSURE_WINDOW_HOURS)

    if perda_diaria <= -abs(MAX_DAILY_LOSS_UNITS):
        return {
            "bloquear": True,
            "codigo": "hard_daily_loss_limit",
            "detalhes": {
                "perda_diaria_unidades": round(perda_diaria, 4),
                "limite_unidades": round(-abs(MAX_DAILY_LOSS_UNITS), 4),
            },
        }

    if exposicao_pendente >= abs(MAX_EXPOSURE_WINDOW_UNITS):
        return {
            "bloquear": True,
            "codigo": "hard_exposure_window_limit",
            "detalhes": {
                "exposicao_pendente_unidades": round(exposicao_pendente, 4),
                "limite_unidades": round(abs(MAX_EXPOSURE_WINDOW_UNITS), 4),
                "janela_horas": EXPOSURE_WINDOW_HOURS,
            },
        }

    return {
        "bloquear": False,
        "codigo": None,
        "detalhes": {
            "perda_diaria_unidades": round(perda_diaria, 4),
            "exposicao_pendente_unidades": round(exposicao_pendente, 4),
            "janela_horas": EXPOSURE_WINDOW_HOURS,
        },
    }


def avaliar_slo_alertas(provider_health, total_avaliacoes_mercado, ciclo_duracao_segundos, drift_alerta=None):
    alertas = []
    disponibilidade = obter_slo_disponibilidade_ciclo(dias=7)
    disponibilidade_val = disponibilidade.get("disponibilidade", 1.0)
    if disponibilidade_val < SLO_CYCLE_AVAILABILITY_MIN:
        alertas.append(
            {
                "severidade": "critical",
                "codigo": "slo_cycle_availability_breach",
                "playbook": "PB-01",
                "detalhes": {
                    "valor": disponibilidade_val,
                    "limite": SLO_CYCLE_AVAILABILITY_MIN,
                    "janela_dias": 7,
                },
            }
        )

    fallback_rate = 0.0
    if total_avaliacoes_mercado > 0:
        fallback_rate = round(provider_health.get("fallback_used", 0) / float(total_avaliacoes_mercado), 4)
    if fallback_rate > SLO_FALLBACK_RATE_MAX:
        severidade = "critical" if fallback_rate >= (SLO_FALLBACK_RATE_MAX * 1.25) else "warning"
        alertas.append(
            {
                "severidade": severidade,
                "codigo": "slo_fallback_rate_breach",
                "playbook": "PB-02",
                "detalhes": {
                    "valor": fallback_rate,
                    "limite": SLO_FALLBACK_RATE_MAX,
                },
            }
        )

    if ciclo_duracao_segundos > SLO_CYCLE_LATENCY_MAX_SECONDS:
        severidade = "critical" if ciclo_duracao_segundos >= (SLO_CYCLE_LATENCY_MAX_SECONDS * 1.5) else "warning"
        alertas.append(
            {
                "severidade": severidade,
                "codigo": "slo_cycle_latency_breach",
                "playbook": "PB-03",
                "detalhes": {
                    "valor": round(ciclo_duracao_segundos, 3),
                    "limite": SLO_CYCLE_LATENCY_MAX_SECONDS,
                },
            }
        )

    if drift_alerta and drift_alerta.get("metrica") == "brier_medio":
        valor = float(drift_alerta.get("valor_atual") or 0.0)
        if valor >= SLO_DRIFT_MAX_BRIER:
            alertas.append(
                {
                    "severidade": "critical",
                    "codigo": "slo_drift_brier_breach",
                    "playbook": "PB-04",
                    "detalhes": {
                        "valor": valor,
                        "limite": SLO_DRIFT_MAX_BRIER,
                        "segmento": f"{drift_alerta.get('segmento_tipo')}={drift_alerta.get('segmento_valor')}",
                    },
                }
            )

    return alertas


async def emitir_alerta_operacional(alerta):
    await alert_service.emitir_alerta_operacional(
        alerta=alerta,
        token=TOKEN,
        chat_id=CANAL_VIP,
        playbook_link=PLAYBOOK_LINK,
        registrar_alerta_fn=registrar_alerta_operacional,
        log_event_fn=log_event,
        bot_cls=Bot,
    )


def enviar_alerta_drift_historico(alerta):
    alert_service.emitir_alerta_drift_historico(
        alerta=alerta,
        token=TOKEN,
        chat_id=CANAL_VIP,
        log_event_fn=log_event,
        bot_cls=Bot,
    )

def obter_media_gols(time_casa, time_fora, liga_key="soccer_epl"):
    xg_casa, xg_fora, fonte = calcular_xg_com_sos(time_casa, time_fora, liga_key)
    return xg_casa, xg_fora, fonte

def atualizar_excel(payload_dict):
    try:
        payload = _json.dumps(payload_dict)
        subprocess.run(
            ["python", EXCEL_PATH, payload],
            cwd=BASE_DIR,
            timeout=30
        )
    except Exception as e:
        print(f"Erro update Excel: {e}")


def calcular_ajuste_prior_ranking(prior_ranking):
    try:
        prior_num = float(prior_ranking)
    except (TypeError, ValueError):
        prior_num = 0.0

    ajuste = prior_num * 0.75
    return max(-6.0, min(6.0, ajuste))


def executar_preflight():
    log_event("startup", "preflight", "scheduler", "start")
    falhas = []
    avisos = []

    garantir_schema_minimo()

    if not TOKEN:
        falhas.append("BOT_TOKEN ausente")

    if not CANAL_VIP:
        falhas.append("CANAL_VIP ausente")

    db_dir = os.path.dirname(DB_PATH)
    if not db_dir or not os.path.isdir(db_dir):
        falhas.append(f"Diretorio do banco invalido: {db_dir}")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.close()
    except Exception as e:
        falhas.append(f"Falha ao abrir banco em {DB_PATH}: {e}")

    schema_ok, missing_items = validar_schema_minimo()
    if not schema_ok:
        falhas.append(f"Schema minimo incompleto: {', '.join(missing_items)}")

    if not os.path.isfile(EXCEL_PATH):
        aviso = f"Arquivo Excel nao encontrado: {EXCEL_PATH}"
        avisos.append(aviso)
        log_event(
            "startup",
            "preflight",
            "excel",
            "warning",
            "non_critical_excel_missing",
            {"arquivo": EXCEL_PATH},
        )

    if falhas:
        log_event(
            "startup",
            "preflight",
            "scheduler",
            "failed",
            "critical_preflight_failed",
            {"falhas": falhas, "avisos": avisos},
        )
        print("Preflight falhou. Corrija os itens criticos antes de iniciar:")
        for item in falhas:
            print(f"- {item}")
        if avisos:
            print("Avisos nao bloqueantes:")
            for item in avisos:
                print(f"- {item}")
        raise SystemExit(1)

    log_event(
        "startup",
        "preflight",
        "scheduler",
        "pass",
        None,
        {"avisos": avisos},
    )

def formatar_sinal_kelly(analise, kelly):
    return dispatch_service.formatar_pick(analise, kelly, carregar_estado_banca)


async def processar_jogos(dry_run=False):
    ciclo_inicio = time.perf_counter()
    ciclo_inicio_watchdog = time.monotonic()
    ciclo_watchdog_disparado = False

    def ciclo_timeout_excedido(contexto):
        nonlocal ciclo_watchdog_disparado
        timeout_segundos = _timeout_ciclo_segundos()
        decorrido = time.monotonic() - ciclo_inicio_watchdog
        if decorrido < timeout_segundos:
            return False

        if not ciclo_watchdog_disparado:
            mensagem = f"[WATCHDOG] Ciclo ultrapassou {timeout_segundos}s - forçando encerramento"
            print(mensagem)
            logging.error(mensagem)
            detalhes = {
                "evento": "watchdog_cycle_timeout",
                "timeout_segundos": timeout_segundos,
                "duracao_segundos": round(decorrido, 3),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "contexto": contexto,
            }
            if not dry_run:
                registrar_alerta_operacional(
                    severidade="critical",
                    codigo="watchdog_cycle_timeout",
                    playbook_id="PB-03",
                    detalhes=detalhes,
                )
            log_event("runtime", "watchdog", "cycle", "critical", "watchdog_cycle_timeout", detalhes)
            ciclo_watchdog_disparado = True
        return True

    if not _garantir_schema_db():
        if not dry_run:
            return
        log_event(
            "runtime",
            "db",
            "bootstrap",
            "warning",
            "db_schema_bootstrap_skipped_dry_run",
            {"detalhe": "seguindo em dry-run com schema mockado"},
        )
    bot = None
    if not dry_run:
        bot = Bot(token=TOKEN)
    agora = datetime.now().strftime("%H:%M")
    if not MINIMAL_RUNTIME_OUTPUT:
        print(f"\n[{agora}] Iniciando análise automática...")

    if KILL_SWITCH and not dry_run:
        registrar_auditoria_acao(
            actor=OPERATOR_ID,
            acao="send_signals",
            efeito="blocked_kill_switch",
            detalhes={"edge_kill_switch": True, "version": EDGE_VERSION},
        )
        registrar_alerta_operacional(
            severidade="critical",
            codigo="kill_switch_active",
            playbook_id="PB-00",
            detalhes={"playbook_link": PLAYBOOK_LINK, "version": EDGE_VERSION},
        )
        log_event("runtime", "guardrail", "kill_switch", "critical", "kill_switch_active", {"version": EDGE_VERSION})
        return

    if not dry_run:
        hard_limits = avaliar_guardrails_hard_limits()
        if hard_limits.get("bloquear"):
            codigo = hard_limits.get("codigo")
            detalhes = hard_limits.get("detalhes", {})
            registrar_auditoria_acao(actor=OPERATOR_ID, acao="send_signals", efeito=f"blocked_{codigo}", detalhes=detalhes)
            registrar_alerta_operacional(severidade="critical", codigo=codigo, playbook_id="PB-05", detalhes=detalhes)
            log_event("runtime", "guardrail", "risk_limits", "critical", codigo, detalhes)
            return

    sinais_hoje = len(buscar_sinais_hoje())
    limite_diario_ativo = MAX_SINAIS_DIA > 0
    if limite_diario_ativo and sinais_hoje >= MAX_SINAIS_DIA:
        if not MINIMAL_RUNTIME_OUTPUT:
            print(f"Limite diário atingido: {sinais_hoje}/{MAX_SINAIS_DIA}")
        return

    conn_check = sqlite3.connect(DB_PATH)
    c_check = conn_check.cursor()
    c_check.execute(
        "SELECT jogo || '|' || mercado FROM sinais WHERE data = ?",
        (datetime.now().strftime("%Y-%m-%d"),)
    )
    ja_enviados = set(row[0] for row in c_check.fetchall())
    conn_check.close()

    jogos_processados = set()
    candidatos = []
    dry_run_discard_counts = {}

    def registrar_descarte_dry_run(jogo_nome, mercado_nome, motivo, detalhes=None):
        if not dry_run:
            return
        chave_motivo = str(motivo or "descarte_indefinido")
        dry_run_discard_counts[chave_motivo] = dry_run_discard_counts.get(chave_motivo, 0) + 1
        sufixo = ""
        if detalhes:
            sufixo = f" | {detalhes}"
        print(f"[dry-run][descartado] {jogo_nome} | {mercado_nome} | {chave_motivo}{sufixo}")

    provider_health = {
        "ok": 0,
        "timeout": 0,
        "http_error": 0,
        "connection_error": 0,
        "empty_payload": 0,
        "unknown_error": 0,
        "invalid_input": 0,
        "fallback_used": 0,
    }
    prior_context_counts = {
        "ok": 0,
        "baixa_amostra": 0,
        "sem_sinal": 0,
    }
    total_avaliacoes_mercado = 0
    jogos_com_fallback_xg: list = []
    _odds_cache: dict = {}

    for liga_key in LIGAS:
        if ciclo_timeout_excedido({"etapa": "liga", "liga_key": liga_key}):
            break

        fetch_result = buscar_jogos_com_odds_com_status(liga_key)
        status = (fetch_result or {}).get("status")
        if status in provider_health:
            provider_health[status] += 1
        else:
            provider_health["unknown_error"] += 1
        jogos = formatar_jogos((fetch_result or {}).get("data", []))

        for jogo in jogos:
            if ciclo_timeout_excedido({"etapa": "jogo", "liga_key": liga_key, "jogo": jogo.get("jogo", "desconhecido")}):
                break

            if jogo["jogo"] in jogos_processados:
                continue
            jogos_processados.add(jogo["jogo"])

            try:
                home = jogo["home_team"]
                away = jogo["away_team"]
                media_casa, media_fora, fonte_dados = obter_media_gols(home, away, liga_key)

                _fonte_lower = fonte_dados.lower()
                if "médias" in _fonte_lower or "medias" in _fonte_lower:
                    jogos_com_fallback_xg.append(jogo["jogo"])

                ajuste_casa, ajuste_fora = calcular_ajuste_forma(home, away)

                advanced_match_analysis = None
                if ADVANCED_PIPELINE_ENABLED and ADVANCED_PIPELINE is not None:
                    try:
                        market_odds = {
                            "home": float(jogo.get("odds", {}).get("casa", 0) or 0),
                            "away": float(jogo.get("odds", {}).get("fora", 0) or 0),
                            "over_2.5": float(jogo.get("odds", {}).get("over_2.5", 0) or 0),
                            "under_2.5": float(jogo.get("odds", {}).get("under_2.5", 0) or 0),
                        }
                        market_odds = {k: v for k, v in market_odds.items() if v > 1.01}
                        if market_odds:
                            advanced_match_analysis = ADVANCED_PIPELINE.analyze_match(
                                match_id=f"{jogo.get('jogo','')}|{jogo.get('horario','')}",
                                home_team=home,
                                away_team=away,
                                division=jogo.get("liga", "Premier League"),
                                country="England",
                                market_odds=market_odds,
                            )
                            media_casa = float(advanced_match_analysis.get("lambda_home", media_casa))
                            media_fora = float(advanced_match_analysis.get("lambda_away", media_fora))
                            fonte_dados = f"{fonte_dados}+HBM_HA_ELO"
                    except (ValueError, TypeError, KeyError, RuntimeError) as e:
                        OBSERVABILITY_SERVICE.warning_payload(
                            job_nome=EXECUCAO_CICLO.get("job_nome") or "analise",
                            jogo=jogo.get("jogo", "unknown"),
                            mercado="multi",
                            etapa="advanced_pipeline",
                            reason_code="advanced_pipeline_failed",
                            error=e,
                        )
                        advanced_match_analysis = None

                primeiro_mercado = True
                for market_cfg in listar_mercados_runtime():
                    if ciclo_timeout_excedido(
                        {
                            "etapa": "mercado",
                            "liga_key": liga_key,
                            "jogo": jogo.get("jogo", "desconhecido"),
                            "mercado": market_cfg.get("mercado"),
                        }
                    ):
                        break

                    mercado = market_cfg["mercado"]
                    odd_key = market_cfg["odd_key"]
                    odd_oponente_key = market_cfg["odd_oponente_key"]
                    total_avaliacoes_mercado += 1
                    contexto_confianca = calcular_confianca_contexto(home, away, jogo["liga"], mercado)
                    confianca = int(contexto_confianca.get("confianca", 50))

                    if "xG" in fonte_dados:
                        confianca = min(100, confianca + 10)
                    if "SOS" in fonte_dados:
                        confianca = min(100, confianca + 5)

                    qualidade_prior = contexto_confianca.get("qualidade_prior", "sem_sinal")
                    if qualidade_prior not in prior_context_counts:
                        qualidade_prior = "sem_sinal"
                    prior_context_counts[qualidade_prior] += 1
                    ajuste_prior = calcular_ajuste_prior_ranking(contexto_confianca.get("prior_ranking", 0.0))

                    odd = jogo["odds"].get(odd_key, 0)
                    odd_oponente_mercado = jogo["odds"].get(odd_oponente_key, 0)
                    source_quality = jogo.get("source_quality", {}).get(mercado, "fallback")

                    sharp_score = 0.0
                    try:
                        abertura = buscar_snapshot_abertura(jogo["jogo"], mercado)
                        snapshots = []
                        if abertura:
                            odd_open = abertura[0] or abertura[1]
                            ts_open = datetime.fromisoformat(abertura[5]) if abertura[5] else datetime.now(timezone.utc)
                            if odd_open:
                                snapshots.append(OddsSnapshot(timestamp=ts_open, odd=float(odd_open), source="abertura"))
                        snapshots.append(OddsSnapshot(timestamp=datetime.now(timezone.utc), odd=float(odd), source="atual"))
                        line = MarketLine(
                            match_id=f"{jogo.get('jogo','')}|{jogo.get('horario','')}",
                            market=mercado,
                            selection=mercado,
                            snapshots=snapshots,
                        )
                        sharp = ADVANCED_SHARP.sharp_score(line=line, our_odd=float(odd), public_bet_pct=0.5)
                        sharp_score = float(sharp.get("sharp_score", 0.0))
                    except Exception:
                        sharp_score = 0.0
                    valid_entrada, motivo_entrada = validar_entrada_analise(jogo, odd)
                    if not valid_entrada:
                        provider_health["invalid_input"] += 1
                        registrar_descarte_dry_run(
                            jogo.get("jogo", "desconhecido"),
                            mercado,
                            motivo_entrada,
                            f"odd={odd}",
                        )
                        if not MINIMAL_RUNTIME_OUTPUT:
                            print(f"Skip entrada {motivo_entrada}: {jogo.get('jogo', 'desconhecido')} | {mercado}")
                        continue

                    chave = f"{jogo['jogo']}|{mercado}"
                    if chave in ja_enviados:
                        registrar_descarte_dry_run(
                            jogo.get("jogo", "desconhecido"),
                            mercado,
                            "ja_enviado_no_dia",
                        )
                        continue

                    dados_analise = {
                        "liga": jogo["liga"],
                        "jogo": jogo["jogo"],
                        "horario": jogo["horario"],
                        "media_gols_casa": media_casa,
                        "media_gols_fora": media_fora,
                        "mercado": mercado,
                        "odd": odd,
                        "ajuste_lesoes": 0.0,
                        "ajuste_motivacao": ajuste_casa,
                        "ajuste_fadiga": ajuste_fora,
                        "confianca_dados": confianca,
                        "estabilidade_odd": 80,
                        "contexto_jogo": 70,
                        "banca": 1000
                    }

                    dados_analise["shadow_mode"] = MODEL_SHADOW_MODE
                    analise = analisar_jogo_com_timeout(
                        dados_analise,
                        jogo=jogo,
                        mercado=mercado,
                        log_dc=primeiro_mercado,
                    )
                    primeiro_mercado = False

                    if analise is None:
                        registrar_descarte_dry_run(
                            jogo.get("jogo", "desconhecido"),
                            mercado,
                            "watchdog_timeout_analise",
                        )
                        continue

                    _registrar_shadow_prediction_runtime(analise, dados_analise)

                    if not DISPATCH_SERVICE.should_dispatch(analise):
                        continue

                    _cache_key = f"{home}|{away}|{liga_key}"
                    if _cache_key not in _odds_cache:
                        _odds_cache[_cache_key] = buscar_odds_todas_casas(liga_key, home, away, mercado)
                    dados_odds = _odds_cache[_cache_key]

                    steam_data = None
                    steam_bonus = 0
                    if dados_odds:
                        abertura = buscar_snapshot_abertura(jogo["jogo"], mercado)
                        if not abertura:
                            salvar_snapshot(jogo["jogo"], mercado, dados_odds, "abertura")
                        else:
                            steam_data = calcular_steam(jogo["jogo"], mercado, dados_odds)
                            if steam_data:
                                steam_bonus = calcular_bonus_edge_score(steam_data)

                    if "fallback" in fonte_dados.lower() or "médias" in fonte_dados.lower() or "medias" in fonte_dados.lower():
                        provider_health["fallback_used"] += 1
                        if not dry_run:
                            registrar_fallback_stats_medias(jogo, mercado, fonte_dados, source_quality)

                    source_quality_low = False
                    if odd_oponente_mercado <= 0:
                        provider_health["missing_odd_oponente"] = provider_health.get("missing_odd_oponente", 0) + 1
                        provider_health["fallback_used"] += 1
                        source_quality_low = True
                    elif source_quality != "sharp":
                        provider_health["source_quality_low"] = provider_health.get("source_quality_low", 0) + 1
                        if not dry_run:
                            registrar_fallback_source_quality_low(jogo, mercado, fonte_dados, source_quality)
                        source_quality_low = True

                    quality_canary_pre_filter = _is_quality_canary_candidate(
                        source_quality_low=source_quality_low,
                        edge=analise.get("ev", 0.0),
                        score=(float(analise.get("edge_score", 0.0) or 0.0) + float(steam_bonus or 0.0)),
                    )

                    escalacao_confirmada, origem_escalacao = inferir_escalacao_confirmada(jogo)
                    variacao_odd_gate = calcular_variacao_odd_gate(steam_data)
                    sinais_hoje_gate = calcular_sinais_hoje_gate(sinais_hoje, len(candidatos))

                    filtro = aplicar_triple_gate({
                        "ev": analise.get("ev", 0),
                        "odd": odd,
                        "odd_oponente_mercado": odd_oponente_mercado,
                        "mercado": mercado,
                        "escalacao_confirmada": escalacao_confirmada,
                        "variacao_odd": variacao_odd_gate,
                        "no_vig_source_quality": source_quality,
                        "prob_modelo_base": analise.get("prob_modelo_base", analise.get("prob_modelo", None)),
                        "prob_modelo": analise.get("prob_modelo", None),
                        "max_sinais_dia": MAX_SINAIS_DIA,
                        "liga": jogo["liga"],
                        "time_casa": home,
                        "time_fora": away,
                    }, sinais_hoje=sinais_hoje_gate)

                    if not filtro.get("aprovado") and not quality_canary_pre_filter:
                        registrar_descarte_dry_run(
                            jogo.get("jogo", "desconhecido"),
                            mercado,
                            filtro.get("reason_code") or "filtro_reprovado",
                            filtro.get("motivo"),
                        )
                        log_event(
                            "runtime",
                            "gate",
                            f"{jogo['jogo']}|{mercado}",
                            "reject",
                            filtro.get("reason_code"),
                            {
                                "bloqueado_em": filtro.get("bloqueado_em"),
                                "origem_escalacao": origem_escalacao,
                                "sinais_hoje_gate": sinais_hoje_gate,
                                "variacao_odd": variacao_odd_gate,
                                "qualidade_prior": qualidade_prior,
                                "amostra_prior": contexto_confianca.get("amostra_prior", 0),
                                "prior_ranking": contexto_confianca.get("prior_ranking", 0.0),
                                "ajuste_prior": round(ajuste_prior, 4),
                            },
                        )
                        continue
                    elif not filtro.get("aprovado") and quality_canary_pre_filter:
                        filtro = dict(filtro)
                        filtro["aprovado"] = True
                        filtro["reason_code"] = "source_quality_low_bypass_canary"

                    policy_v2_result = None
                    if POLICY_V2_ENABLED and gate_ev_steam is not None and EV_POLICY_V2 is not None and STEAM_POLICY_V2 is not None:
                        mercado_policy = mapear_mercado_policy_v2(mercado)
                        odd_abertura = (steam_data or {}).get("odd_abertura", odd)
                        odd_atual = (steam_data or {}).get("odd_atual", odd)
                        book_ref = "pinnacle" if (dados_odds or {}).get("odd_pinnacle") else "default"
                        minutos_jogo = minutos_ate_jogo(jogo.get("horario"))
                        try:
                            policy_v2_result = gate_ev_steam(
                                mercado=mercado_policy,
                                ev_calculado=float(analise.get("ev", 0.0)),
                                odd_abertura=float(odd_abertura),
                                odd_atual=float(odd_atual),
                                book=book_ref,
                                minutos_ate_jogo=float(minutos_jogo),
                                ev_policy=EV_POLICY_V2,
                                steam_policy=STEAM_POLICY_V2,
                            )
                        except Exception as exc:
                            log_event(
                                "runtime",
                                "policy_v2",
                                f"{jogo['jogo']}|{mercado}",
                                "warning",
                                "policy_v2_eval_failed",
                                {"erro": str(exc)},
                            )
                            policy_v2_result = None

                    if policy_v2_result is not None and not policy_v2_result.aprovado:
                        if log_policy_v2_rejection is not None:
                            try:
                                log_policy_v2_rejection(
                                    shadow_mode=POLICY_V2_SHADOW_MODE,
                                    prediction_id=analise.get("prediction_id", ""),
                                    league=jogo.get("liga", ""),
                                    market=mercado,
                                    team_home=home,
                                    team_away=away,
                                    odds=float(odd),
                                    ev=float(analise.get("ev", 0.0)),
                                    edge_score=float(analise.get("edge_score", 0.0)),
                                    reject_reason=policy_v2_result.motivo_final,
                                    odds_reference=(steam_data or {}).get("odd_atual"),
                                )
                            except Exception as exc:
                                log_event(
                                    "runtime",
                                    "policy_v2",
                                    f"{jogo['jogo']}|{mercado}",
                                    "warning",
                                    "policy_v2_reject_log_failed",
                                    {"erro": str(exc)},
                                )

                        log_event(
                            "runtime",
                            "policy_v2",
                            f"{jogo['jogo']}|{mercado}",
                            "reject" if not POLICY_V2_SHADOW_MODE else "shadow_reject",
                            "policy_v2_gate_reject",
                            {
                                "motivo": policy_v2_result.motivo_final,
                                "shadow_mode": POLICY_V2_SHADOW_MODE,
                            },
                        )
                        if policy_v2_blocks is None:
                            should_block = not POLICY_V2_SHADOW_MODE
                        else:
                            should_block = policy_v2_blocks(policy_v2_result, POLICY_V2_SHADOW_MODE)
                        if should_block:
                            registrar_descarte_dry_run(
                                jogo.get("jogo", "desconhecido"),
                                mercado,
                                "policy_v2_gate_reject",
                                policy_v2_result.motivo_final,
                            )
                            continue

                    penalizacao = filtro.get("penalizacao_score", 0)
                    pipeline_bonus = 0
                    if advanced_match_analysis:
                        market_key_map = {
                            "1x2_casa": "home",
                            "1x2_fora": "away",
                            "over_2.5": "over_2.5",
                            "under_2.5": "under_2.5",
                        }
                        mk = market_key_map.get(mercado)
                        if mk:
                            for opp in advanced_match_analysis.get("opportunities", []):
                                if getattr(opp, "market", None) == mk:
                                    pipeline_bonus = max(0, min(6, int(getattr(opp, "edge", 0.0) * 100)))
                                    break

                    sharp_bonus = max(0, min(8, int(sharp_score * 10)))
                    edge_score_final = min(100, analise["edge_score"] + steam_bonus + penalizacao + sharp_bonus + pipeline_bonus)
                    score_prior = edge_score_final + ajuste_prior
                    analise["edge_score"] = edge_score_final
                    analise["steam_bonus"] = steam_bonus
                    analise["fonte_dados"] = fonte_dados

                    if ADVANCED_PIPELINE_ENABLED:
                        registrar_diagnostico_modelo(
                            match_id=f"{jogo.get('jogo','')}|{jogo.get('horario','')}",
                            market=mercado,
                            lambda_home=float(media_casa),
                            lambda_away=float(media_fora),
                            sharp_score=sharp_score,
                            edge=float(analise.get("ev", 0.0)),
                            shrinkage_home=float((advanced_match_analysis or {}).get("hbm_shrinkage_home", 0.0)),
                            shrinkage_away=float((advanced_match_analysis or {}).get("hbm_shrinkage_away", 0.0)),
                            detalhes={
                                "source_quality": source_quality,
                                "sharp_bonus": sharp_bonus,
                                "pipeline_bonus": pipeline_bonus,
                            },
                        )

                    analise.setdefault("reasoning_trace", {})
                    edge_cutoff_runtime = float(analise.get("edge_cutoff_segment", MIN_EDGE_SCORE) or MIN_EDGE_SCORE)
                    conf_cutoff_runtime = max(
                        float(MIN_CONFIANCA_EFETIVA),
                        float(analise.get("confidence_threshold", MIN_CONFIANCA_EFETIVA) or MIN_CONFIANCA_EFETIVA),
                    )
                    if dry_run and DRY_RUN_RELAXED_GATES:
                        edge_cutoff_runtime = -1.0
                        conf_cutoff_runtime = -1.0
                    analise["reasoning_trace"]["gate_inputs"] = {
                        "min_edge_score": edge_cutoff_runtime,
                        "min_confianca_efetiva": conf_cutoff_runtime,
                        "edge_score_final": edge_score_final,
                        "confianca": confianca,
                        "filtro_aprovado": bool(filtro.get("aprovado")),
                    }

                    quality_canary_active = _is_quality_canary_candidate(
                        source_quality_low=source_quality_low,
                        edge=analise.get("ev", 0.0),
                        score=edge_score_final,
                    )
                    analise["reasoning_trace"]["quality_canary"] = {
                        "enabled": _quality_canary_enabled(),
                        "activated": bool(quality_canary_active),
                        "source_quality_low": bool(source_quality_low),
                        "edge": float(analise.get("ev", 0.0) or 0.0),
                        "score": float(edge_score_final or 0.0),
                    }

                    passou_gate_runtime = bool(
                        filtro["aprovado"] and edge_score_final >= edge_cutoff_runtime and confianca >= conf_cutoff_runtime
                    )
                    if passou_gate_runtime or quality_canary_active:
                        candidatos.append({
                            "analise": analise,
                            "jogo": jogo,
                            "mercado": mercado,
                            "score": edge_score_final,
                            "score_prior": round(score_prior, 4),
                            "fonte": fonte_dados,
                            "confianca": confianca,
                            "qualidade_prior": qualidade_prior,
                            "amostra_prior": contexto_confianca.get("amostra_prior", 0),
                            "prior_ranking": contexto_confianca.get("prior_ranking", 0.0),
                            "ajuste_prior": round(ajuste_prior, 4),
                            "policy_v2": {
                                "aplicado": policy_v2_result is not None,
                                "aprovado": (policy_v2_result.aprovado if policy_v2_result is not None else None),
                                "shadow_mode": POLICY_V2_SHADOW_MODE,
                            },
                            "canary_quality": bool(quality_canary_active),
                            "canary_reason": "source_quality_low_bypass_canary" if quality_canary_active else None,
                            "liga_key": liga_key,
                            "dados_odds": dados_odds
                        })
                    else:
                        motivos_gate = []
                        if not filtro["aprovado"]:
                            motivos_gate.append("filtro_reprovado")
                        if edge_score_final < edge_cutoff_runtime:
                            motivos_gate.append("edge_score_abaixo_minimo")
                        if confianca < conf_cutoff_runtime:
                            motivos_gate.append("confianca_abaixo_cutoff")
                        analise["reasoning_trace"]["gate_discard"] = motivos_gate
                        registrar_descarte_dry_run(
                            jogo.get("jogo", "desconhecido"),
                            mercado,
                            "+".join(motivos_gate) if motivos_gate else "gate_discard",
                            (
                                f"score={edge_score_final:.1f}/min={edge_cutoff_runtime:.1f}; "
                                f"conf={confianca}/min={conf_cutoff_runtime:.1f}"
                            ),
                        )

            except Exception as e:
                provider_health["connection_error"] += 1
                if MINIMAL_RUNTIME_OUTPUT:
                    print("-> FAIL")
                    import traceback
                    traceback.print_exc()
                    logging.exception("FAIL em analise")
                else:
                    print(f"Erro ao processar {jogo['jogo']}: {e}")

        if ciclo_watchdog_disparado:
            break

    candidatos = aplicar_penalizacao_correlacao_ranking(candidatos)
    candidatos = aplicar_cap_por_jogo(candidatos)
    if limite_diario_ativo:
        vagas_restantes = max(0, MAX_SINAIS_DIA - sinais_hoje)
        selecionados = candidatos[:vagas_restantes]
    else:
        vagas_restantes = len(candidatos)
        selecionados = candidatos
    selecionados, suprimidos_canary = aplicar_canary_operacional(
        selecionados,
        ratio=CANARY_RATIO,
        enabled=(CANARY_MODE_ENABLED and not dry_run),
    )

    if suprimidos_canary:
        log_event(
            "runtime",
            "canary",
            "selection",
            "warning",
            "canary_ratio_applied",
            {
                "ratio": CANARY_RATIO,
                "selecionados": len(selecionados),
                "suprimidos": len(suprimidos_canary),
            },
        )

    if not MINIMAL_RUNTIME_OUTPUT:
        print(f"Candidatos encontrados: {len(candidatos)}")
        print(f"Sinais a enviar: {len(selecionados)}")

    sinais_enviados = 0
    primeiro_sinal = sinais_hoje == 0

    for item in selecionados:
        analise = item["analise"]
        jogo = item["jogo"]

        sinais_abertos = contar_sinais_abertos()
        sinais_liga = contar_sinais_liga_hoje(analise["liga"])
        sinais_mesmo_jogo = contar_sinais_mesmo_jogo_abertos(analise["jogo"])

        kelly = calcular_kelly(
            prob_modelo=analise.get("prob_modelo", 0.55),
            odd=analise["odd"],
            edge_score=analise["edge_score"],
            sinais_abertos=sinais_abertos,
            liga=analise["liga"],
            sinais_liga_hoje=sinais_liga,
            sinais_mesmo_jogo_abertos=sinais_mesmo_jogo,
        )

        if not isinstance(kelly, dict):
            registrar_descarte_dry_run(jogo.get("jogo", "desconhecido"), item.get("mercado", "?"), "kelly_payload_invalido")
            if not MINIMAL_RUNTIME_OUTPUT:
                print(f"Kelly inválido: {jogo['jogo']} — resposta não é dict")
            continue

        quality_canary_pick = bool(item.get("canary_quality"))

        if not kelly.get("aprovado") and not quality_canary_pick:
            registrar_descarte_dry_run(
                jogo.get("jogo", "desconhecido"),
                item.get("mercado", "?"),
                "kelly_reprovado",
                kelly.get("motivo", "motivo_indefinido"),
            )
            if not MINIMAL_RUNTIME_OUTPUT:
                print(f"Kelly bloqueou: {jogo['jogo']} — {kelly.get('motivo', 'motivo_indefinido')}")
            continue

        if quality_canary_pick:
            kelly_final_pct, valor_reais = _apply_quality_canary_stake_override(kelly)
            kelly["aprovado"] = True
            kelly["kelly_final_pct"] = kelly_final_pct
            kelly["valor_reais"] = valor_reais
            kelly["tier"] = kelly.get("tier") or "padrao"
            kelly["motivo"] = item.get("canary_reason") or "source_quality_low_bypass_canary"
            _emit_quality_canary_log(analise.get("ev", 0.0), analise.get("edge_score", 0.0))
        else:
            required_fields = ["tier", "kelly_final_pct", "valor_reais"]
            if any(field not in kelly for field in required_fields):
                registrar_descarte_dry_run(jogo.get("jogo", "desconhecido"), item.get("mercado", "?"), "kelly_payload_incompleto")
                if not MINIMAL_RUNTIME_OUTPUT:
                    print(f"Kelly inválido: {jogo['jogo']} — payload incompleto")
                continue

            try:
                kelly_final_pct = float(kelly["kelly_final_pct"])
                valor_reais = float(kelly["valor_reais"])
            except (TypeError, ValueError):
                registrar_descarte_dry_run(jogo.get("jogo", "desconhecido"), item.get("mercado", "?"), "kelly_valor_nao_numerico")
                if not MINIMAL_RUNTIME_OUTPUT:
                    print(f"Kelly inválido: {jogo['jogo']} — valores não numéricos")
                continue

            if not math.isfinite(kelly_final_pct) or not math.isfinite(valor_reais) or kelly_final_pct < 0 or valor_reais < 0:
                registrar_descarte_dry_run(jogo.get("jogo", "desconhecido"), item.get("mercado", "?"), "kelly_stake_fora_faixa")
                if not MINIMAL_RUNTIME_OUTPUT:
                    print(f"Kelly inválido: {jogo['jogo']} — stake fora da faixa segura")
                continue

        stake_reais = valor_reais
        stake_unidades = round(kelly_final_pct / 1, 2)
        analise["stake_reais"] = stake_reais
        analise["stake_unidades"] = stake_unidades

        msg = formatar_sinal_kelly(analise, kelly)
        if not msg:
            continue

        # INTEGRATION: bloqueia sinais já enviados no mesmo dia (mesma liga/jogo/mercado) antes do envio Telegram.
        if not dry_run:
            team_home, team_away = _split_match_name(analise.get("jogo", ""))
            qtd_dup = contar_sinais_duplicados_mesmo_dia(
                analise.get("liga", ""),
                team_home,
                team_away,
                analise.get("mercado", ""),
            )
            if qtd_dup > 0:
                _registrar_duplicate_skip(
                    analise.get("liga", ""),
                    team_home,
                    team_away,
                    analise.get("mercado", ""),
                )
                log_event(
                    "runtime",
                    "duplicates",
                    analise.get("jogo", ""),
                    "skip",
                    "duplicate_same_day",
                    {"market": analise.get("mercado", "")},
                )
                continue

        if dry_run:
            sinais_enviados += 1
            print(f"[dry-run] Simulado sinal: {jogo['jogo']} | {item['mercado']} | Score:{analise['edge_score']}")
            continue

        msg_vip = await bot.send_message(chat_id=CANAL_VIP, text=msg)
        message_id_vip = msg_vip.message_id
        message_id_free = None

        if primeiro_sinal and sinais_enviados == 0:
            msg_free = await bot.send_message(chat_id=CANAL_FREE, text=msg)
            message_id_free = msg_free.message_id
            if not MINIMAL_RUNTIME_OUTPUT:
                print(f"Enviado FREE: {jogo['jogo']} | {item['mercado']}")

        try:
            sinal_id = inserir_sinal(
                liga=analise["liga"],
                jogo=analise["jogo"],
                mercado=analise["mercado"],
                odd=analise["odd"],
                ev=analise["ev"],
                score=analise["edge_score"],
                stake=stake_unidades,
                message_id_vip=message_id_vip,
                message_id_free=message_id_free,
                horario=jogo["horario"],
                canary_tag="canary_quality" if quality_canary_pick else None,
            )
        except Exception as e:
            marcar_ciclo_degradado("critical_persistence_insert_sinal", {"jogo": analise.get("jogo"), "erro": str(e)})
            continue

        try:
            registrar_aposta_clv(sinal_id, analise["jogo"], analise["mercado"],
                                  analise["odd"], analise.get("prob_modelo", 0.5))
        except Exception as e:
            if not MINIMAL_RUNTIME_OUTPUT:
                print(f"Erro CLV: {e}")

        if item.get("dados_odds") and analise.get("steam_bonus", 0) > 0:
            steam = calcular_steam(jogo["jogo"], item["mercado"], item["dados_odds"])
            if steam:
                salvar_steam_evento(sinal_id, jogo["jogo"], item["mercado"],
                                    steam, analise["steam_bonus"])

        try:
            tip = "Casa" if analise["mercado"] == "1x2_casa" else "Over 2.5"
            atualizar_excel({
                "acao": "nova_aposta",
                "aposta": {
                    "id": str(sinal_id),
                    "data": datetime.now().strftime("%Y-%m-%d"),
                    "hora": datetime.now().strftime("%H:%M"),
                    "liga": analise["liga"],
                    "jogo": analise["jogo"],
                    "mercado": analise["mercado"],
                    "tip": tip,
                    "odd_entrada": analise["odd"],
                    "odd_fechamento": None,
                    "ev": analise.get("ev", 0),
                    "edge_score": analise["edge_score"],
                    "tier": kelly["tier"],
                    "prob_modelo": analise.get("prob_modelo", 0.55),
                    "confianca": item["confianca"],
                    "steam": analise.get("steam_bonus", 0),
                    "kelly_pct": kelly["kelly_final_pct"],
                    "unidades": stake_unidades,
                    "version": EDGE_VERSION,
                    "resultado": None,
                    "retorno": None,
                    "banca_apos": None,
                    "notas": analise.get("fonte_dados", "")
                }
            })
        except Exception as e:
            if not MINIMAL_RUNTIME_OUTPUT:
                print(f"Erro update Excel (sinal): {e}")

        sinais_enviados += 1
        steam_info = f" | Steam:+{analise['steam_bonus']}pts" if analise.get("steam_bonus", 0) > 0 else ""
        if not MINIMAL_RUNTIME_OUTPUT:
            print(f"Sinal #{sinal_id}: {jogo['jogo']} | {item['mercado']} | Score:{analise['edge_score']} | Kelly:{kelly['kelly_final_pct']}%=R${stake_reais:.2f}{steam_info}")

    if not MINIMAL_RUNTIME_OUTPUT:
        logging.info("[%s] Concluído. %s sinais enviados.", agora, sinais_enviados)
        logging.info(
            "Health summary: "
            f"ok={provider_health['ok']} "
            f"timeout={provider_health['timeout']} "
            f"http_error={provider_health['http_error']} "
            f"connection_error={provider_health['connection_error']} "
            f"empty_payload={provider_health['empty_payload']} "
            f"unknown_error={provider_health['unknown_error']} "
            f"invalid_input={provider_health['invalid_input']} "
            f"fallback_used={provider_health['fallback_used']} "
            f"missing_odd_oponente={provider_health.get('missing_odd_oponente', 0)} "
            f"source_quality_low={provider_health.get('source_quality_low', 0)}"
        )
    if dry_run and dry_run_discard_counts:
        print("[dry-run][resumo_descartes]")
        for motivo, qtd in sorted(dry_run_discard_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"  - {motivo}: {qtd}")
    drift_alert = avaliar_alerta_drift_minimo(provider_health, total_avaliacoes_mercado)
    if drift_alert:
        log_event(
            "runtime",
            "drift",
            "fallback_rate",
            "alert",
            "drift_min_threshold_exceeded",
            drift_alert,
        )

    provider_error_rate = calcular_provider_error_rate(provider_health)
    if (not dry_run) and provider_error_rate >= PROVIDER_ERROR_RATE_MAX:
        marcar_ciclo_degradado(
            "provider_error_rate_high",
            {
                "provider_error_rate": provider_error_rate,
                "limiar": PROVIDER_ERROR_RATE_MAX,
            },
        )
        await emitir_alerta_operacional(
            {
                "severidade": "critical",
                "codigo": "provider_error_rate_high",
                "playbook": "PB-02",
                "detalhes": {
                    "provider_error_rate": provider_error_rate,
                    "limiar": PROVIDER_ERROR_RATE_MAX,
                },
            }
        )

    EXECUCAO_STATS["provider_health"] = dict(provider_health)
    EXECUCAO_STATS["total_avaliacoes_mercado"] = int(total_avaliacoes_mercado)

    ciclo_duracao = round(time.perf_counter() - ciclo_inicio, 4)
    EXECUCAO_STATS["duracao_segundos"] = ciclo_duracao

    if not dry_run:
        for alerta in avaliar_slo_alertas(
            provider_health=provider_health,
            total_avaliacoes_mercado=total_avaliacoes_mercado,
            ciclo_duracao_segundos=ciclo_duracao,
            drift_alerta=drift_alert,
        ):
            await emitir_alerta_operacional(alerta)

    log_event(
        "scheduler",
        "cycle_totals",
        "analise",
        EXECUCAO_CICLO["status"],
        EXECUCAO_CICLO["reason_codes"][0] if EXECUCAO_CICLO["reason_codes"] else None,
        {
            "candidatos": len(candidatos),
            "enviados": sinais_enviados,
            "max_diario": MAX_SINAIS_DIA,
            "provider_health": provider_health,
            "prior_context_counts": prior_context_counts,
            "jogos_fallback_xg": jogos_com_fallback_xg,
        },
    )

async def monitorar_janela_expandida():
    todas_ligas = LIGAS_COPA + LIGAS_FIM_DE_SEMANA
    jogos_novos = 0

    for liga_key in todas_ligas:
        jogos = buscar_jogos_janela_expandida(liga_key, horas=72)
        for jogo in jogos:
            registrar_jogo_monitorado(jogo)
            jogos_novos += 1

    atualizar_modo_jogos()

    em_observacao = buscar_jogos_observacao()
    for row in em_observacao:
        jogo = row[0]
        marcar_notificado(jogo)

    if not MINIMAL_RUNTIME_OUTPUT:
        print(f"Janela expandida: {jogos_novos} jogos monitorados silenciosamente")

async def monitorar_steam_sinais_ativos():
    bot = Bot(token=TOKEN)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, jogo, mercado, liga, horario FROM sinais
        WHERE status = 'pendente' AND data = ?
    ''', (datetime.now().strftime("%Y-%m-%d"),))
    ativos = c.fetchall()
    conn.close()

    if not ativos:
        return

    for sinal_id, jogo, mercado, liga_nome, horario in ativos:
        try:
            liga_key = LIGA_KEY_MAP.get(liga_nome, "soccer_epl")
            times = jogo.split(" vs ")
            if len(times) != 2:
                continue

            home, away = times
            dados = buscar_odds_todas_casas(liga_key, home, away, mercado)
            if not dados:
                continue

            salvar_snapshot(jogo, mercado, dados, "snapshot")

            steam = calcular_steam(jogo, mercado, dados)
            if steam and steam["steam_confirmado"]:
                bonus = calcular_bonus_edge_score(steam)
                if bonus > 0:
                    msg = gerar_alerta_steam(jogo, mercado, steam, sinal_id)
                    await bot.send_message(chat_id=CANAL_VIP, text=msg)
                    print(f"Alerta steam: {jogo} | +{bonus}pts")

        except Exception as e:
            print(f"Erro steam {jogo}: {e}")

async def verificar_clv_fechamento():
    pendentes = buscar_sinais_para_fechar()
    if not pendentes:
        return

    agora = datetime.now(timezone.utc)

    for sinal_id, jogo, mercado, liga_nome in pendentes:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT horario FROM sinais WHERE id = ?", (sinal_id,))
        row = c.fetchone()
        conn.close()

        if not row or not row[0]:
            continue

        try:
            horario_jogo = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            minutos_para_jogo = (horario_jogo - agora).total_seconds() / 60

            if -10 <= minutos_para_jogo <= 10:
                liga_key = LIGA_KEY_MAP.get(liga_nome, "soccer_epl")
                odd_fechamento = buscar_odd_fechamento_pinnacle(jogo, mercado, liga_key)
                if odd_fechamento:
                    clv = atualizar_clv(sinal_id, odd_fechamento)
                    if clv is not None:
                        sinal = "+" if clv >= 0 else ""
                        print(f"CLV #{sinal_id}: {sinal}{clv:.2f}% {'✅' if clv > 0 else '⚠️'}")
        except Exception as e:
            print(f"Erro CLV #{sinal_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FIX-10: settlement com side-effects extraídos em funções auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def _registrar_shadow_prediction_runtime(analise, dados_analise):
    if not MODEL_SHADOW_MODE:
        return

    payload = analise.get("shadow_payload") or {}
    prob_baseline = payload.get("prob_baseline", analise.get("prob_modelo_raw", analise.get("prob_modelo", 0.5)))
    prob_advanced = payload.get("prob_advanced", analise.get("prob_modelo", prob_baseline))

    try:
        registrar_shadow_prediction(
            liga=str(dados_analise.get("liga") or analise.get("liga") or ""),
            jogo=str(dados_analise.get("jogo") or analise.get("jogo") or ""),
            mercado=str(dados_analise.get("mercado") or analise.get("mercado") or ""),
            prob_baseline=float(prob_baseline),
            prob_advanced=float(prob_advanced),
            prediction_id_baseline=payload.get("prediction_id_baseline") or analise.get("prediction_id"),
            prediction_id_advanced=payload.get("prediction_id_advanced") or analise.get("prediction_id"),
            shadow_mode=True,
            detalhes={
                "ev": analise.get("ev"),
                "edge_score": analise.get("edge_score"),
                "segment_threshold": payload.get("segment_threshold"),
                "market_features": payload.get("market_features"),
            },
        )
    except Exception as e:
        log_event(
            "runtime",
            "shadow",
            f"{dados_analise.get('jogo', 'unknown')}|{dados_analise.get('mercado', 'unknown')}",
            "warning",
            "shadow_register_failed",
            {"erro": str(e)},
        )


def evaluate_shadow_promotion(window_days=21, bootstrap_iters=2000):
    rows = listar_shadow_settled_por_janela(dias=window_days)
    if not rows:
        return {
            "n": 0,
            "mean_brier_gain": 0.0,
            "mean_clv_gain": 0.0,
            "p_value": 1.0,
            "recommend_promote": False,
            "reason": "insufficient_data",
        }

    brier_gains = []
    clv_gains = []
    for row in rows:
        brier_base = row[2]
        brier_adv = row[3]
        clv_base = row[4]
        clv_adv = row[5]
        if brier_base is None or brier_adv is None:
            continue
        brier_gains.append(float(brier_base) - float(brier_adv))
        if clv_base is not None and clv_adv is not None:
            clv_gains.append(float(clv_adv) - float(clv_base))

    n = len(brier_gains)
    if n < 30:
        return {
            "n": n,
            "mean_brier_gain": round(sum(brier_gains) / n, 6) if n else 0.0,
            "mean_clv_gain": round(sum(clv_gains) / len(clv_gains), 6) if clv_gains else 0.0,
            "p_value": 1.0,
            "recommend_promote": False,
            "reason": "insufficient_sample_min_30",
        }

    mean_brier_gain = sum(brier_gains) / n
    mean_clv_gain = (sum(clv_gains) / len(clv_gains)) if clv_gains else 0.0

    iters = max(200, int(bootstrap_iters))
    non_positive_count = 0
    for _ in range(iters):
        sample = [brier_gains[random.randrange(n)] for _ in range(n)]
        sample_mean = sum(sample) / n
        if sample_mean <= 0.0:
            non_positive_count += 1
    p_value = non_positive_count / iters

    recommend = bool(mean_brier_gain > 0.0 and p_value < 0.05 and mean_clv_gain >= 0.0)
    return {
        "n": n,
        "mean_brier_gain": round(mean_brier_gain, 6),
        "mean_clv_gain": round(mean_clv_gain, 6),
        "p_value": round(p_value, 6),
        "recommend_promote": recommend,
        "reason": "ok" if recommend else "criteria_not_met",
    }


async def verificar_resultados_automatico():
    contexto_settlement = {
        "TOKEN": TOKEN,
        "CANAL_VIP": CANAL_VIP,
        "CANAL_FREE": CANAL_FREE,
        "DB_PATH": DB_PATH,
        "BOT_DATA_DIR": BOT_DATA_DIR,
        "MINIMAL_RUNTIME_OUTPUT": MINIMAL_RUNTIME_OUTPUT,
        "MODEL_SHADOW_MODE": MODEL_SHADOW_MODE,
        "MODEL_SHADOW_PROMOTION_WINDOW_DAYS": MODEL_SHADOW_PROMOTION_WINDOW_DAYS,
        "MODEL_SHADOW_BOOTSTRAP_ITERS": MODEL_SHADOW_BOOTSTRAP_ITERS,
        "LIGA_KEY_MAP": LIGA_KEY_MAP,
        "log_event": log_event,
        "marcar_ciclo_degradado": marcar_ciclo_degradado,
        "atualizar_resultado": atualizar_resultado,
        "atualizar_banca": atualizar_banca,
        "atualizar_brier": atualizar_brier,
        "carregar_estado_banca": carregar_estado_banca,
        "atualizar_excel": atualizar_excel,
        "atualizar_fixture_referencia": atualizar_fixture_referencia,
        "buscar_odd_fechamento_pinnacle": buscar_odd_fechamento_pinnacle,
        "atualizar_clv": atualizar_clv,
        "liquidar_shadow_predictions_por_sinal": liquidar_shadow_predictions_por_sinal,
        "evaluate_shadow_promotion": evaluate_shadow_promotion,
        "gerar_excel": lambda: __import__("data.exportar_excel", fromlist=["gerar_excel"]).gerar_excel(),
    }
    await settlement_service.processar_settlement(contexto_settlement)

async def enviar_resumo_diario():
    from data.database import resumo_mensal
    from data.database import resumo_calibracao
    from data.clv_brier import calcular_metricas

    resumo = resumo_mensal()
    total = resumo[0] or 0
    vitorias = resumo[1] or 0
    derrotas = resumo[2] or 0
    lucro = resumo[3] or 0.0
    win_rate = (vitorias / total * 100) if total > 0 else 0

    metricas = calcular_metricas()
    relatorio = gerar_relatorio_diario()
    imprimir_relatorio(relatorio)

    b = relatorio["banca"]
    clv_linha = ""
    brier_linha = ""

    if metricas["total_apostas_clv"] > 0:
        sinal = "+" if metricas["clv_medio"] >= 0 else ""
        clv_linha = f"CLV Médio: {sinal}{metricas['clv_medio']}%\n"

    if metricas["total_apostas_brier"] > 0:
        status = "✅" if metricas["brier_medio"] < 0.25 else "⚠️"
        brier_linha = f"Brier Score: {metricas['brier_medio']:.4f} {status}\n"

    cal = resumo_calibracao(50)
    if cal["faltam"] > 0:
        calibracao_linha = f"📊 Calibração: {cal['total']}/50 apostas\n"
    elif cal.get("alerta"):
        calibracao_linha = f"⚠️ WR real {cal['win_rate_real']}% abaixo do esperado\n"
    elif cal.get("calibrado"):
        calibracao_linha = f"✅ Modelo calibrado: {cal['win_rate_real']}% WR\n"
    else:
        calibracao_linha = ""

    msg = dispatch_service.formatar_resumo_diario(
        {
            "total": total,
            "vitorias": vitorias,
            "derrotas": derrotas,
            "lucro": lucro,
            "win_rate": win_rate,
            "banca": b["atual"],
            "roi": relatorio["performance"]["roi_acumulado_pct"],
            "drawdown": b["drawdown_atual_pct"],
            "clv_linha": clv_linha,
            "brier_linha": brier_linha,
            "calibracao_linha": calibracao_linha,
        }
    )

    await dispatch_service.enviar_resumo(msg, token=TOKEN, canal_vip=CANAL_VIP, canal_free=CANAL_FREE)

    try:
        atualizar_excel({"acao": "full_refresh"})
        print("Excel atualizado (full refresh).")
    except Exception as e:
        print(f"Erro Excel: {e}")

    print("Resumo enviado.")

def rodar_analise():
    executar_job_guardado("analise", 60, lambda: asyncio.run(processar_jogos()))

def rodar_verificacao():
    executar_job_guardado("verificacao", 5, lambda: asyncio.run(verificar_resultados_automatico()))

def rodar_resumo():
    executar_job_guardado("resumo", 60, lambda: asyncio.run(enviar_resumo_diario()))

def rodar_clv():
    executar_job_guardado("clv", 5, lambda: asyncio.run(verificar_clv_fechamento()))

def rodar_steam():
    executar_job_guardado("steam", 30, lambda: asyncio.run(monitorar_steam_sinais_ativos()))

def rodar_janela_expandida():
    executar_job_guardado("janela_expandida", 120, lambda: asyncio.run(monitorar_janela_expandida()))


def rodar_janela_expandida_boot():
    executar_job_guardado(
        "janela_expandida",
        120,
        lambda: asyncio.run(monitorar_janela_expandida()),
        force_once=True,
    )


def rodar_analise_boot():
    executar_job_guardado("analise", 60, lambda: asyncio.run(processar_jogos()), force_once=True)

def atualizar_stats_semanalmente():
    print("Atualizando médias de gols...")
    atualizar_todas_ligas()
    print("Atualizando xG...")
    from data.xg_understat import atualizar_xg_todas_ligas
    atualizar_xg_todas_ligas()

    try:
        snapshot = registrar_snapshot_qualidade_semanal()
        log_event(
            "runtime",
            "telemetry",
            "quality_weekly",
            "ok",
            None,
            {
                "referencia_semana": snapshot.get("referencia_semana"),
                "segmentos": len(snapshot.get("segmentos", [])),
            },
        )
    except Exception as e:
        marcar_ciclo_degradado("quality_snapshot_failed", {"erro": str(e)})

    try:
        alerta = avaliar_drift_historico(
            janela=DRIFT_HISTORICO_JANELA,
            min_persistencia=DRIFT_HISTORICO_MIN_PERSISTENCIA,
        )
        if alerta:
            log_event("runtime", "drift", "quality_rolling", "alert", "drift_historico_threshold_exceeded", alerta)
            enviar_alerta_drift_historico(alerta)
    except Exception as e:
        marcar_ciclo_degradado("quality_drift_eval_failed", {"erro": str(e)})

    print("Stats atualizadas.")


def rodar_backtest_recorrente():
    script = os.path.join(BASE_DIR, "scripts", "backtest_moving_window.py")
    panel_script = os.path.join(BASE_DIR, "scripts", "slo_panel.py")
    if not os.path.isfile(script):
        log_event("runtime", "backtest", "moving_window", "warning", "backtest_script_missing", {"script": script})
        return

    try:
        out = subprocess.run(["python", script], cwd=BASE_DIR, capture_output=True, text=True, timeout=120)
        status = "ok" if out.returncode == 0 else "degraded"
        if out.returncode != 0:
            marcar_ciclo_degradado("backtest_window_failed", {"rc": out.returncode, "stdout": out.stdout[-400:]})
        registrar_auditoria_acao(
            actor=OPERATOR_ID,
            acao="backtest_moving_window",
            efeito=status,
            detalhes={"returncode": out.returncode, "version": EDGE_VERSION},
        )
        log_event(
            "runtime",
            "backtest",
            "moving_window",
            status,
            None,
            {
                "returncode": out.returncode,
                "stdout_tail": out.stdout[-200:] if out.stdout else "",
            },
        )
        if os.path.isfile(panel_script):
            subprocess.run(["python", panel_script], cwd=BASE_DIR, timeout=60)
    except Exception as e:
        marcar_ciclo_degradado("backtest_window_exception", {"erro": str(e)})

def iniciar_scheduler():
    log_event("startup", "boot", "scheduler", "start")
    garantir_schema_minimo()
    executar_preflight()
    garantir_tabela_execucoes()
    if SHOW_STARTUP_BANNER:
        print(
            MAGENTA
            + """
                                                                          
  ▄▄▄▄▄▄▄                      ▄▄▄▄▄▄                                 ▄▄ 
 █▀██▀▀▀     █▄               █▀██▀▀▀█▄           █▄                   ██
   ██        ██    ▄▄           ██▄▄▄█▀▄         ▄██▄                  ██
   ████   ▄████ ▄████ ▄█▀█▄     ██▀▀▀  ████▄▄███▄ ██ ▄███▄ ▄███▀ ▄███▄ ██
   ██     ██ ██ ██ ██ ██▄█▀   ▄ ██     ██   ██ ██ ██ ██ ██ ██    ██ ██ ██
   ▀█████▄█▀███▄▀████▄▀█▄▄▄   ▀██▀    ▄█▀  ▄▀███▀▄██▄▀███▀▄▀███▄▄▀███▀▄██
                   ██                                                    
                 ▀▀▀                                                     
"""
                        + ANSI_RESET
        )
        print(f"Score mínimo: {MIN_EDGE_SCORE}/100")
        print(f"Confiança mínima: {MIN_CONFIANCA}/100")
        print(f"Kelly fracionado: 1/4 com teto 3%")
        print(f"SOS: ativo")
        print(f"Janela expandida: 72h clássicos / 48h copa / 12h liga")
        print(f"Excel: atualização automática ativa")
        print("\nHorários programados:")
        print("  09:00 — Análise da manhã")
        print("  16:00 — Análise da tarde")
        print("  A cada 2h — Monitoramento janela expandida (silencioso)")
        print("  A cada 5min — CLV fechamento")
        print("  A cada 30min — Steam monitoring")
        print("  A cada 5min (17h-23h) — Verificação de resultados")
        print("  23:30 — Resumo diário + Excel full refresh")
        print("  Segunda 06:00 — Atualização de stats + xG")
        print("  Segunda 06:30 — Backtest janela móvel + promoção")
        print("")

    schedule.every().day.at("09:00").do(rodar_analise)
    schedule.every().day.at("16:00").do(rodar_analise)
    schedule.every(2).hours.do(rodar_janela_expandida)
    schedule.every(5).minutes.do(rodar_clv)
    schedule.every(30).minutes.do(rodar_steam)

    for hora in range(17, 24):
        for minuto in range(0, 60, 5):
            horario = f"{hora:02d}:{minuto:02d}"
            if horario == "23:30":
                schedule.every().day.at("23:30").do(rodar_resumo)
            else:
                schedule.every().day.at(horario).do(rodar_verificacao)

    schedule.every().monday.at("06:00").do(atualizar_stats_semanalmente)
    schedule.every().monday.at("06:30").do(rodar_backtest_recorrente)

    log_event("startup", "boot", "scheduler", "ready")

    rodar_janela_expandida_boot()
    rodar_analise_boot()

    while True:
        schedule.run_pending()
        _esperar_ocioso_com_animacao(60)


def executar_dry_run_once():
    log_event("runtime", "dry_run", "scheduler", "start")
    try:
        asyncio.run(processar_jogos(dry_run=True))
        log_event("runtime", "dry_run", "scheduler", "end")
        return 0
    except Exception as e:
        log_event("runtime", "dry_run", "scheduler", "failed", "dry_run_exception", {"erro": str(e)})
        return 1


def executar_check_duplicates():
    if not _garantir_schema_db():
        return 1

    duplicados = listar_sinais_duplicados_mesmo_dia()
    if not duplicados:
        print("Nenhuma duplicidade same-day encontrada em sinais.")
        return 0

    print("Duplicidades same-day encontradas:")
    for item in duplicados:
        print(
            f"{item['date']} | {item['league']} | {item['team_home']} vs {item['team_away']} "
            f"| {item['market']} | count={item['count']}"
        )
    return 1

if __name__ == "__main__":
    if "--check-duplicates" in sys.argv:
        raise SystemExit(executar_check_duplicates())

    if "--dry-run-once" in sys.argv:
        raise SystemExit(executar_dry_run_once())

    try:
        iniciar_scheduler()
    except KeyboardInterrupt:
        log_event("runtime", "shutdown", "scheduler", "stopped", "keyboard_interrupt")
        if not MINIMAL_RUNTIME_OUTPUT:
            print("\nScheduler encerrado pelo operador.")
