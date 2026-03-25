import asyncio
import sys
import os
import math
import schedule
import time
import sqlite3
import subprocess
import json as _json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "model"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))

from analisar_jogo import analisar_jogo, formatar_sinal
from filtros import aplicar_triple_gate
from database import (
    DB_PATH,
    buscar_sinais_hoje,
    finalizar_execucao_job,
    garantir_schema_minimo,
    garantir_tabela_execucoes,
    iniciar_execucao_job,
    inserir_sinal,
    validar_schema_minimo,
)
from coletar_odds import (
    buscar_jogos_com_odds,
    buscar_jogos_com_odds_com_status,
    formatar_jogos,
    atualizar_contadores_provider_health,
)
from atualizar_stats import carregar_medias, atualizar_todas_ligas
from forma_recente import calcular_ajuste_forma, calcular_confianca_contexto
from xg_understat import calcular_media_gols_com_xg
from sos_ajuste import calcular_xg_com_sos
from clv_brier import registrar_aposta_clv, atualizar_brier, buscar_sinais_para_fechar, buscar_odd_fechamento_pinnacle, atualizar_clv
from kelly_banca import calcular_kelly, atualizar_banca, contar_sinais_abertos, contar_sinais_liga_hoje, contar_sinais_mesmo_jogo_abertos, gerar_relatorio_diario, imprimir_relatorio, carregar_estado_banca
from steam_monitor import buscar_odds_todas_casas, salvar_snapshot, buscar_snapshot_abertura, calcular_steam, calcular_bonus_edge_score, salvar_steam_evento, gerar_alerta_steam
from janela_monitoramento import buscar_jogos_janela_expandida, registrar_jogo_monitorado, atualizar_modo_jogos, buscar_jogos_observacao, marcar_notificado, LIGAS_COPA, LIGAS_FIM_DE_SEMANA
from quality_telemetry import registrar_snapshot_qualidade_semanal, avaliar_drift_historico
from signal_policy import MIN_EDGE_SCORE, MIN_CONFIANCA
from runtime_gate_context import inferir_escalacao_confirmada, calcular_variacao_odd_gate, calcular_sinais_hoje_gate

from dotenv import load_dotenv
from telegram import Bot

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CANAL_VIP = os.getenv("CANAL_VIP")
CANAL_FREE = os.getenv("CANAL_FREE")
LOG_LEVEL = os.getenv("EDGE_LOG_LEVEL", "normal").strip().lower()

MAX_SINAIS_DIA = 10
MAX_MERCADOS_POR_JOGO = 2
CORRELACAO_PENALTY_STEP = 2.0
DRIFT_MIN_FALLBACK_LIMIAR = 0.35
DRIFT_HISTORICO_MIN_PERSISTENCIA = 3
DRIFT_HISTORICO_JANELA = 4
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "logs", "update_excel.py")
BASE_DIR = os.path.dirname(__file__)

EXECUCAO_CICLO = {
    "job_nome": None,
    "status": "ok",
    "reason_codes": [],
}

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


def resetar_execucao_ciclo(job_nome):
    EXECUCAO_CICLO["job_nome"] = job_nome
    EXECUCAO_CICLO["status"] = "ok"
    EXECUCAO_CICLO["reason_codes"] = []


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
    log_event("scheduler", "job_guard", job_nome, "start", None, {"janela_chave": janela_chave})

    try:
        executor()
    except Exception as e:
        marcar_ciclo_falha("job_exception", {"erro": str(e), "janela_chave": janela_chave})
    finally:
        status_final = EXECUCAO_CICLO["status"]
        reason_code_final = EXECUCAO_CICLO["reason_codes"][0] if EXECUCAO_CICLO["reason_codes"] else None
        finalizar_execucao_job(
            job_nome,
            janela_chave,
            status_final,
            reason_code=reason_code_final,
            detalhes_json={"reason_codes": EXECUCAO_CICLO["reason_codes"]},
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


def enviar_alerta_drift_historico(alerta):
    if not alerta:
        return
    if not TOKEN or not CANAL_VIP:
        return

    msg = (
        "ALERTA DRIFT (rolling)\n\n"
        f"Metrica: {alerta.get('metrica')}\n"
        f"Segmento: {alerta.get('segmento_tipo')}={alerta.get('segmento_valor')}\n"
        f"Periodo: {alerta.get('periodo_inicio')} ate {alerta.get('periodo_fim')}\n"
        f"Persistencia minima: {alerta.get('min_persistencia')} semanas\n"
        f"Valor atual: {alerta.get('valor_atual')}"
    )

    def _log_task_exception(task):
        try:
            exc = task.exception()
        except Exception as cb_err:
            log_event(
                "runtime",
                "drift",
                "telegram",
                "warning",
                "drift_alert_send_failed",
                {"erro": str(cb_err)},
            )
            return

        if exc:
            log_event(
                "runtime",
                "drift",
                "telegram",
                "warning",
                "drift_alert_send_failed",
                {"erro": str(exc)},
            )

    try:
        bot = Bot(token=TOKEN)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(bot.send_message(chat_id=CANAL_VIP, text=msg))
            return

        task = loop.create_task(bot.send_message(chat_id=CANAL_VIP, text=msg))
        task.add_done_callback(_log_task_exception)
    except Exception as e:
        log_event("runtime", "drift", "telegram", "warning", "drift_alert_send_failed", {"erro": str(e)})

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

    # Keep prior influence bounded so it informs ordering without dominating edge score.
    ajuste = prior_num * 0.75
    return max(-6.0, min(6.0, ajuste))


def executar_preflight():
    log_event("startup", "preflight", "scheduler", "start")
    falhas = []
    avisos = []

    # Bootstrap required execution table before schema validation to avoid first-run false negatives.
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
    if analise["decisao"] == "DESCARTAR":
        return None

    emoji_tier = {"elite": "🔥", "premium": "⚡", "padrao": "✅"}
    emoji = emoji_tier.get(kelly["tier"], "✅")

    mercados_legivel = {
        "1x2_casa": "Vitória do time da casa",
        "1x2_fora": "Vitória do time visitante",
        "over_2.5":  "Mais de 2.5 gols na partida",
        "under_2.5": "Menos de 2.5 gols na partida",
    }
    mercado_texto = mercados_legivel.get(analise["mercado"], analise["mercado"])

    horario_raw = analise.get("horario", "")
    try:
        dt = datetime.strptime(horario_raw, "%Y-%m-%dT%H:%M:%SZ")
        dt_brasil = dt - timedelta(hours=3)
        horario_formatado = dt_brasil.strftime("%d/%m/%Y — %H:%M")
    except Exception:
        horario_formatado = horario_raw

    estado = carregar_estado_banca()
    banca_atual = estado["banca_atual"]

    steam_linha = ""
    if analise.get("steam_bonus", 0) > 0:
        steam_linha = f"🔥 Steam: +{analise['steam_bonus']}pts (sharp money)\n"

    sos_linha = ""
    if "+SOS" in analise.get("fonte_dados", ""):
        sos_linha = f"📐 SOS: força do adversário ajustada\n"

    msg = (
        f"{emoji} SINAL EDGE PROTOCOL — {kelly['tier'].upper()}\n\n"
        f"🏆 {analise['liga']}\n"
        f"⚽ {analise['jogo']}\n"
        f"📅 {horario_formatado}\n\n"
        f"📌 Aposta: {mercado_texto}\n"
        f"💰 Odd: {analise['odd']}\n"
        f"📊 EDGE Score: {analise['edge_score']}/100\n"
        f"🎯 EV: {analise['ev_percentual']}\n"
        f"{steam_linha}"
        f"{sos_linha}"
        f"\n🏦 Kelly: {kelly['kelly_final_pct']}% da banca\n"
        f"💵 Valor: R${analise['stake_reais']:.2f}\n"
        f"   (Banca: R${banca_atual:.2f})\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    return msg

async def processar_jogos(dry_run=False):
    bot = None
    if not dry_run:
        bot = Bot(token=TOKEN)
    agora = datetime.now().strftime("%H:%M")
    print(f"\n[{agora}] Iniciando análise automática...")

    sinais_hoje = len(buscar_sinais_hoje())
    if sinais_hoje >= MAX_SINAIS_DIA:
        print(f"Limite diário atingido: {sinais_hoje}/{MAX_SINAIS_DIA}")
        return

    conn_check = sqlite3.connect("data/edge_protocol.db")
    c_check = conn_check.cursor()
    c_check.execute(
        "SELECT jogo || '|' || mercado FROM sinais WHERE data = ?",
        (datetime.now().strftime("%Y-%m-%d"),)
    )
    ja_enviados = set(row[0] for row in c_check.fetchall())
    conn_check.close()

    jogos_processados = set()
    candidatos = []
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

    for liga_key in LIGAS:
        fetch_result = buscar_jogos_com_odds_com_status(liga_key)
        atualizar_contadores_provider_health(provider_health, fetch_result.get("status"))
        dados_api = fetch_result.get("data", [])
        jogos = formatar_jogos(dados_api)

        for jogo in jogos:
            if jogo["jogo"] in jogos_processados:
                continue
            jogos_processados.add(jogo["jogo"])

            try:
                home = jogo["home_team"]
                away = jogo["away_team"]
                media_casa, media_fora, fonte_dados = obter_media_gols(home, away, liga_key)
                ajuste_casa, ajuste_fora = calcular_ajuste_forma(home, away)

                primeiro_mercado = True
                for market_cfg in listar_mercados_runtime():
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
                    valid_entrada, motivo_entrada = validar_entrada_analise(jogo, odd)
                    if not valid_entrada:
                        provider_health["invalid_input"] += 1
                        print(f"Skip entrada {motivo_entrada}: {jogo.get('jogo', 'desconhecido')} | {mercado}")
                        continue

                    chave = f"{jogo['jogo']}|{mercado}"
                    if chave in ja_enviados:
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

                    analise = analisar_jogo(dados_analise, log_dc=primeiro_mercado)
                    primeiro_mercado = False

                    if analise["decisao"] == "DESCARTAR":
                        continue

                    dados_odds = buscar_odds_todas_casas(liga_key, home, away, mercado)
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

                    if odd_oponente_mercado <= 0:
                        provider_health["missing_odd_oponente"] = provider_health.get("missing_odd_oponente", 0) + 1
                        provider_health["fallback_used"] += 1
                    elif source_quality != "sharp":
                        provider_health["source_quality_low"] = provider_health.get("source_quality_low", 0) + 1

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
                        "liga": jogo["liga"],
                        "time_casa": home,
                        "time_fora": away,
                    }, sinais_hoje=sinais_hoje_gate)

                    if not filtro.get("aprovado"):
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

                    penalizacao = filtro.get("penalizacao_score", 0)
                    edge_score_final = min(100, analise["edge_score"] + steam_bonus + penalizacao)
                    score_prior = edge_score_final + ajuste_prior
                    analise["edge_score"] = edge_score_final
                    analise["steam_bonus"] = steam_bonus
                    analise["fonte_dados"] = fonte_dados

                    if filtro["aprovado"] and edge_score_final >= MIN_EDGE_SCORE and confianca >= MIN_CONFIANCA:
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
                            "liga_key": liga_key,
                            "dados_odds": dados_odds
                        })

            except Exception as e:
                provider_health["connection_error"] += 1
                print(f"Erro ao processar {jogo['jogo']}: {e}")

    candidatos = aplicar_penalizacao_correlacao_ranking(candidatos)
    candidatos = aplicar_cap_por_jogo(candidatos)
    vagas_restantes = MAX_SINAIS_DIA - sinais_hoje
    selecionados = candidatos[:vagas_restantes]

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
            print(f"Kelly inválido: {jogo['jogo']} — resposta não é dict")
            continue

        if not kelly.get("aprovado"):
            print(f"Kelly bloqueou: {jogo['jogo']} — {kelly.get('motivo', 'motivo_indefinido')}")
            continue

        required_fields = ["tier", "kelly_final_pct", "valor_reais"]
        if any(field not in kelly for field in required_fields):
            print(f"Kelly inválido: {jogo['jogo']} — payload incompleto")
            continue

        try:
            kelly_final_pct = float(kelly["kelly_final_pct"])
            valor_reais = float(kelly["valor_reais"])
        except (TypeError, ValueError):
            print(f"Kelly inválido: {jogo['jogo']} — valores não numéricos")
            continue

        if not math.isfinite(kelly_final_pct) or not math.isfinite(valor_reais) or kelly_final_pct < 0 or valor_reais < 0:
            print(f"Kelly inválido: {jogo['jogo']} — stake fora da faixa segura")
            continue

        stake_reais = valor_reais
        stake_unidades = round(kelly_final_pct / 1, 2)
        analise["stake_reais"] = stake_reais
        analise["stake_unidades"] = stake_unidades

        msg = formatar_sinal_kelly(analise, kelly)
        if not msg:
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
                horario=jogo["horario"]
            )
        except Exception as e:
            marcar_ciclo_degradado("critical_persistence_insert_sinal", {"jogo": analise.get("jogo"), "erro": str(e)})
            continue

        # CLV tracking
        try:
            registrar_aposta_clv(sinal_id, analise["jogo"], analise["mercado"],
                                  analise["odd"], analise.get("prob_modelo", 0.5))
        except Exception as e:
            print(f"Erro CLV: {e}")

        # Steam evento
        if item.get("dados_odds") and analise.get("steam_bonus", 0) > 0:
            steam = calcular_steam(jogo["jogo"], item["mercado"], item["dados_odds"])
            if steam:
                salvar_steam_evento(sinal_id, jogo["jogo"], item["mercado"],
                                    steam, analise["steam_bonus"])

        # Atualiza Excel com nova aposta
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
                    "resultado": None,
                    "retorno": None,
                    "banca_apos": None,
                    "notas": analise.get("fonte_dados", "")
                }
            })
        except Exception as e:
            print(f"Erro update Excel (sinal): {e}")

        sinais_enviados += 1
        steam_info = f" | Steam:+{analise['steam_bonus']}pts" if analise.get("steam_bonus", 0) > 0 else ""
        print(f"Sinal #{sinal_id}: {jogo['jogo']} | {item['mercado']} | Score:{analise['edge_score']} | Kelly:{kelly['kelly_final_pct']}%=R${stake_reais:.2f}{steam_info}")

    print(f"[{agora}] Concluído. {sinais_enviados} sinais enviados.")
    print(
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

    print(f"Janela expandida: {jogos_novos} jogos monitorados silenciosamente")

async def monitorar_steam_sinais_ativos():
    bot = Bot(token=TOKEN)
    conn = sqlite3.connect("data/edge_protocol.db")
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
        conn = sqlite3.connect("data/edge_protocol.db")
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

async def verificar_resultados_automatico():
    from verificar_resultados import buscar_resultado_jogo, avaliar_mercado
    from database import atualizar_resultado, atualizar_fixture_referencia
    from exportar_excel import gerar_excel

    bot = Bot(token=TOKEN)
    conn = sqlite3.connect("data/edge_protocol.db")
    c = conn.cursor()
    c.execute(
        """
        SELECT id, jogo, mercado, odd, horario, fixture_id_api, fixture_data_api, liga
        FROM sinais
        WHERE status = 'pendente'
        """
    )
    pendentes = c.fetchall()
    conn.close()

    if not pendentes:
        return

    print(f"\nVerificando {len(pendentes)} sinais pendentes...")
    resultado_registrado = False

    for sinal in pendentes:
        if len(sinal) < 7:
            log_event(
                "runtime",
                "settlement",
                "pending_row",
                "warning",
                "pending_row_shape_invalid",
                {"row_len": len(sinal)},
            )
            continue

        sinal_id = sinal[0]
        jogo = sinal[1]
        mercado = sinal[2]
        odd = sinal[3]
        horario = sinal[4]
        fixture_id_api = sinal[5]
        fixture_data_api = sinal[6]
        liga = sinal[7] if len(sinal) >= 8 else None
        try:
            times = jogo.split(" vs ")
            if len(times) != 2:
                continue

            time_casa, time_fora = times
            resultado = buscar_resultado_jogo(
                time_casa.strip(),
                time_fora.strip(),
                data=fixture_data_api,
                horario=horario,
                fixture_id=fixture_id_api,
                liga=liga,
            )

            if resultado and (resultado.get("fixture_id_api") or resultado.get("fixture_data_api")):
                try:
                    atualizar_fixture_referencia(
                        sinal_id,
                        fixture_id_api=resultado.get("fixture_id_api"),
                        fixture_data_api=resultado.get("fixture_data_api"),
                    )
                except Exception as e:
                    print(f"Erro persistindo fixture #{sinal_id}: {e}")

            if not resultado or resultado["status"] != "finalizado":
                continue

            avaliacao = avaliar_mercado(resultado, mercado, odd)
            if not avaliacao:
                continue

            try:
                atualizar_resultado(sinal_id, avaliacao["resultado"], avaliacao["lucro"])
            except Exception as e:
                marcar_ciclo_degradado("critical_persistence_update_resultado", {"sinal_id": sinal_id, "erro": str(e)})
                continue
            resultado_registrado = True

            # Atualiza banca
            try:
                estado = atualizar_banca(avaliacao["lucro"])
                print(f"Banca: R${estado['banca_atual']:.2f}")
            except Exception as e:
                print(f"Erro banca: {e}")

            # Brier Score
            try:
                acertou = avaliacao["resultado"] == "verde"
                brier = atualizar_brier(sinal_id, acertou)
                if brier is not None:
                    print(f"Brier #{sinal_id}: {brier:.4f} {'✅' if brier < 0.25 else '⚠️'}")
            except Exception as e:
                print(f"Erro Brier: {e}")

            # Reação Telegram
            conn2 = sqlite3.connect("data/edge_protocol.db")
            c2 = conn2.cursor()
            c2.execute("SELECT message_id_vip, message_id_free FROM sinais WHERE id = ?",
                       (sinal_id,))
            ids = c2.fetchone()
            conn2.close()

            if ids:
                reacao = "✅" if avaliacao["resultado"] == "verde" else "❌"
                if ids[0]:
                    try:
                        await bot.set_message_reaction(
                            chat_id=CANAL_VIP,
                            message_id=ids[0],
                            reaction=[reacao]
                        )
                    except Exception as e:
                        print(f"Erro reação VIP #{sinal_id}: {e}")
                if ids[1]:
                    try:
                        await bot.set_message_reaction(
                            chat_id=CANAL_FREE,
                            message_id=ids[1],
                            reaction=[reacao]
                        )
                    except Exception as e:
                        print(f"Erro reação FREE #{sinal_id}: {e}")

            # Atualiza Excel com resultado
            try:
                estado_banca = carregar_estado_banca()
                atualizar_excel({
                    "acao": "resultado",
                    "aposta": {
                        "id": str(sinal_id),
                        "odd_fechamento": None,
                        "resultado": avaliacao["resultado"].capitalize(),
                        "retorno": avaliacao["lucro"],
                        "banca_apos": estado_banca["banca_atual"],
                        "data": datetime.now().strftime("%Y-%m-%d")
                    }
                })
            except Exception as e:
                print(f"Erro update Excel (resultado): {e}")

            print(f"Resultado: #{sinal_id} — {avaliacao['resultado'].upper()}")

        except Exception as e:
            print(f"Erro #{sinal_id}: {e}")

    if resultado_registrado:
        try:
            gerar_excel()
            print("Excel atualizado.")
        except Exception as e:
            print(f"Erro Excel: {e}")

async def enviar_resumo_diario():
    from database import resumo_mensal
    from database import resumo_calibracao
    from clv_brier import calcular_metricas

    bot = Bot(token=TOKEN)
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

    msg = (
        f"📊 RESUMO DO DIA\n\n"
        f"Sinais: {total} | ✅ {vitorias} | ❌ {derrotas}\n"
        f"Win Rate: {win_rate:.0f}%\n"
        f"Lucro: {lucro:+.1f} unidades\n\n"
        f"💰 Banca: R${b['atual']:.2f}\n"
        f"📈 ROI: {relatorio['performance']['roi_acumulado_pct']:+.2f}%\n"
        f"📉 Drawdown: {b['drawdown_atual_pct']:.1f}%\n"
        f"{clv_linha}"
        f"{brier_linha}"
        f"{calibracao_linha}"
        f"\n━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )

    await bot.send_message(chat_id=CANAL_VIP, text=msg)
    await bot.send_message(chat_id=CANAL_FREE, text=msg)

    # Full refresh do Excel no resumo diário
    try:
        atualizar_excel({"acao": "full_refresh"})
        print("Excel atualizado (full refresh).")
    except Exception as e:
        print(f"Erro Excel: {e}")

    print("Resumo enviado.")

def rodar_analise():
    executar_job_guardado("analise", 60, lambda: asyncio.run(processar_jogos()))

def rodar_verificacao():
    executar_job_guardado("verificacao", 30, lambda: asyncio.run(verificar_resultados_automatico()))

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
    from xg_understat import atualizar_xg_todas_ligas
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

def iniciar_scheduler():
    log_event("startup", "boot", "scheduler", "start")
    garantir_schema_minimo()
    executar_preflight()
    garantir_tabela_execucoes()
    print("=== SCHEDULER EDGE PROTOCOL ATIVO ===")
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
    print("  A cada 30min (17h-23h) — Verificação de resultados")
    print("  23:30 — Resumo diário + Excel full refresh")
    print("  Segunda 06:00 — Atualização de stats + xG")
    print("\nAguardando próximo horário...\n")

    schedule.every().day.at("09:00").do(rodar_analise)
    schedule.every().day.at("16:00").do(rodar_analise)
    schedule.every(2).hours.do(rodar_janela_expandida)
    schedule.every(5).minutes.do(rodar_clv)
    schedule.every(30).minutes.do(rodar_steam)

    for hora in range(17, 24):
        for minuto in ["00", "30"]:
            horario = f"{hora:02d}:{minuto}"
            if horario == "23:30":
                schedule.every().day.at("23:30").do(rodar_resumo)
            else:
                schedule.every().day.at(horario).do(rodar_verificacao)

    schedule.every().monday.at("06:00").do(atualizar_stats_semanalmente)

    log_event("startup", "boot", "scheduler", "ready")

    rodar_janela_expandida_boot()
    rodar_analise_boot()

    while True:
        schedule.run_pending()
        time.sleep(60)


def executar_dry_run_once():
    log_event("runtime", "dry_run", "scheduler", "start")
    try:
        asyncio.run(processar_jogos(dry_run=True))
        log_event("runtime", "dry_run", "scheduler", "end")
        return 0
    except Exception as e:
        log_event("runtime", "dry_run", "scheduler", "failed", "dry_run_exception", {"erro": str(e)})
        return 1

if __name__ == "__main__":
    if "--dry-run-once" in sys.argv:
        raise SystemExit(executar_dry_run_once())

    try:
        iniciar_scheduler()
    except KeyboardInterrupt:
        log_event("runtime", "shutdown", "scheduler", "stopped", "keyboard_interrupt")
        print("\nScheduler encerrado pelo operador.")