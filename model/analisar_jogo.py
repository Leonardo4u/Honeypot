import os
import uuid
import json
import logging
import traceback
from datetime import datetime

from model.poisson import (
    calcular_probabilidades,
    calcular_prob_over_under,
    calcular_prob_btts,
    ajuste_contextual,
    log_comparacao,
)
from model.edge_score import (
    calcular_ev,
    ev_para_score,
    calcular_edge_score,
    calcular_stake,
    decisao_sinal,
    classificar_recomendacao,
    montar_reasoning_trace,
    calcular_kelly_fracionado,
    MIN_CONFIDENCE_ACTIONABLE,
)
from model.calibrator import BucketCalibrator, CalibratorRegistry
from model.picks_log import PickLogger
from model.market_features import no_vig_probability, build_market_features, blend_probability
from model.contextual_features import get_h2h_features, get_travel_bucket


logger = logging.getLogger(__name__)


def _log_structured_warning(jogo, mercado, etapa, reason_code):
    payload = {
        "jogo": jogo,
        "mercado": mercado,
        "etapa": etapa,
        "reason_code": reason_code,
        "traceback": traceback.format_exc(),
    }
    logger.warning("analisar_jogo_warning %s", json.dumps(payload, ensure_ascii=False))


BOT_DATA_DIR = os.getenv(
    "BOT_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
)

# INTEGRATION: caminho central de calibracao de probabilidades via BOT_DATA_DIR.
CALIBRACAO_PROB_PATH = os.path.join(BOT_DATA_DIR, "calibracao_prob.json")
# INTEGRATION: caminho central de log por pick via BOT_DATA_DIR.
PICKS_LOG_PATH = os.path.join(BOT_DATA_DIR, "picks_log.csv")


def _carregar_calibrador_prob():
    if os.path.exists(CALIBRACAO_PROB_PATH):
        try:
            return CalibratorRegistry.load(CALIBRACAO_PROB_PATH)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            try:
                return BucketCalibrator.load(CALIBRACAO_PROB_PATH)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # Fallback seguro: pass-through caso arquivo exista mas esteja inválido.
                _log_structured_warning(
                    jogo=None,
                    mercado=None,
                    etapa="carregar_calibrador_prob",
                    reason_code="calibration_load_fallback",
                )
                return BucketCalibrator()
    return BucketCalibrator()


def _calibrator_is_fitted(calibrator):
    if isinstance(calibrator, CalibratorRegistry):
        global_fit = bool(getattr(calibrator.global_calibrator, "is_fitted", False))
        segment_fit = any(bool(getattr(ref.calibrator, "is_fitted", False)) for ref in calibrator.by_league.values())
        segment_fit = segment_fit or any(
            bool(getattr(ref.calibrator, "is_fitted", False)) for ref in calibrator.by_league_market.values()
        )
        return global_fit or segment_fit
    return bool(getattr(calibrator, "is_fitted", False))


def _predict_calibrated_probability(prob_ajustada, liga, mercado):
    if isinstance(PROB_CALIBRATOR, CalibratorRegistry):
        return PROB_CALIBRATOR.predict(prob_ajustada, liga=liga, mercado=mercado)
    return PROB_CALIBRATOR.predict(prob_ajustada)


def _obter_threshold_segmentado(liga, mercado):
    default_cfg = {
        "ev_floor": 0.04,
        "confidence_floor": float(MIN_CONFIDENCE_ACTIONABLE),
        "edge_cutoff": 65.0,
        "versao": "default",
    }
    try:
        from data.database import obter_segment_threshold

        cfg = obter_segment_threshold(liga, mercado)
        if not cfg:
            return default_cfg
        return {
            "ev_floor": float(cfg.get("ev_floor", default_cfg["ev_floor"])),
            "confidence_floor": float(cfg.get("confidence_floor", default_cfg["confidence_floor"])),
            "edge_cutoff": float(cfg.get("edge_cutoff", default_cfg["edge_cutoff"])),
            "versao": str(cfg.get("versao", "db")),
        }
    except Exception:
        return default_cfg


def _contextual_factor_avancado(dados):
    base = (
        float(dados.get("ajuste_lesoes", 0) or 0)
        + float(dados.get("ajuste_motivacao", 0) or 0)
        + float(dados.get("ajuste_fadiga", 0) or 0)
    )

    # Ajuste leve orientado por contexto; mantém comportamento anterior se dados ausentes.
    h2h = get_h2h_features(
        str(dados.get("time_casa") or ""),
        str(dados.get("time_fora") or ""),
        h2h_rows=dados.get("h2h_rows"),
    )
    h2h_games = int(h2h.get("h2h_games", 0) or 0)
    h2h_home = float(h2h.get("h2h_win_rate_home", 0.5) or 0.5)
    h2h_component = 0.0
    if h2h_games > 0:
        h2h_component = ((h2h_home - 0.5) * 0.03) * float(h2h.get("h2h_shrinkage_weight", 0.0) or 0.0)

    travel_bucket = get_travel_bucket(dados.get("cidade_casa"), dados.get("cidade_fora"))
    travel_component = {
        "local": 0.01,
        "regional": 0.0,
        "nacional": -0.005,
        "intercontinental": -0.015,
    }.get(travel_bucket, 0.0)

    match_date = dados.get("horario") or datetime.utcnow().isoformat()
    rest_days_home = float(dados.get("rest_days_home", 0) or 0)
    rest_days_away = float(dados.get("rest_days_away", 0) or 0)
    if rest_days_home <= 0:
        from model.contextual_features import get_rest_days

        rest_days_home = float(
            get_rest_days(str(dados.get("time_casa") or ""), match_date, fixture_history=dados.get("fixture_history"))
        )
    if rest_days_away <= 0:
        from model.contextual_features import get_rest_days

        rest_days_away = float(
            get_rest_days(str(dados.get("time_fora") or ""), match_date, fixture_history=dados.get("fixture_history"))
        )
    rest_component = max(-0.02, min(0.02, (rest_days_home - rest_days_away) * 0.0025))

    return float(base + h2h_component + travel_component + rest_component)


PROB_CALIBRATOR = _carregar_calibrador_prob()
# INTEGRATION: logger de picks para auditoria/ciclo de calibracao.
PICK_LOGGER = PickLogger(PICKS_LOG_PATH)


def _registrar_pick(result: dict, dados: dict):
    """Registra o pick analisado no CSV de observabilidade."""
    try:
        PICK_LOGGER.append_pick(
            prediction_id=result["prediction_id"],
            league=result.get("liga", dados.get("liga", "")),
            market=result.get("mercado", dados.get("mercado", "")),
            match_name=result.get("jogo", dados.get("jogo", "")),
            odds_at_pick=float(result.get("odd", dados.get("odd", 0.0) or 0.0)),
            implied_prob=float(result.get("prob_implicita", 0.0) or 0.0),
            raw_prob_model=float(result.get("prob_modelo_raw", result.get("prob_modelo", 0.0)) or 0.0),
            calibrated_prob_model=float(result.get("prob_modelo", 0.0) or 0.0),
            calibrator_fitted=bool((result.get("reasoning_trace") or {}).get("calibrator_fitted", False)),
            confidence_dados=float(dados.get("confianca_dados", 70) or 70),
            estabilidade_odd=float(dados.get("estabilidade_odd", 70) or 70),
            contexto_jogo=float(dados.get("contexto_jogo", 70) or 70),
            edge_score=float(result.get("edge_score", 0.0) or 0.0),
            kelly_fraction=float(result.get("kelly_bruto_frac", 0.0) or 0.0),
            kelly_stake=float(result.get("stake_reais", 0.0) or 0.0),
            bank_used=float(dados.get("banca", 1000) or 1000),
            recomendacao_acao=result.get("recomendacao_acao", "SKIP"),
            reasoning_trace=result.get("reasoning_trace", {}),
        )
    except (KeyError, TypeError, ValueError, OSError):
        # Falha de log nao deve quebrar ciclo principal de decisao.
        _log_structured_warning(
            jogo=result.get("jogo", dados.get("jogo", "unknown")),
            mercado=result.get("mercado", dados.get("mercado", "unknown")),
            etapa="registrar_pick",
            reason_code="pick_logger_failed",
        )
        return


def analisar_jogo(dados, log_dc=True):
    """
    Recebe um dicionário com os dados do jogo e retorna
    a análise completa com EDGE Score e decisão.

    Parâmetros do dicionário 'dados':
    - liga:             nome da liga
    - jogo:             "Time Casa vs Time Fora"
    - horario:          horário do jogo
    - media_gols_casa:  média de gols marcados pelo time da casa
    - media_gols_fora:  média de gols marcados pelo time de fora
    - mercado:          "1x2_casa" | "over_2.5" | "btts_sim"
    - odd:              odd disponível na casa de apostas
    - ajuste_lesoes:    fator de ajuste por lesões (-0.10 a 0.0)
    - ajuste_motivacao: fator de ajuste por motivação (-0.05 a 0.05)
    - ajuste_fadiga:    fator de ajuste por fadiga (-0.08 a 0.0)
    - confianca_dados:  qualidade dos dados (0-100)
    - estabilidade_odd: estabilidade da odd (0-100)
    - contexto_jogo:    contexto geral (0-100)
    - banca:            banca atual em reais
    """

    casa = dados["media_gols_casa"]
    fora = dados["media_gols_fora"]
    mercado = dados["mercado"]
    odd = dados["odd"]
    liga = dados.get("liga", None)

    prediction_id = str(uuid.uuid4())

    # ── Poisson + Dixon-Coles (passa liga para rho correto por liga) ──
    probs_1x2 = calcular_probabilidades(casa, fora, liga=liga)
    probs_ou = calcular_prob_over_under(casa, fora, linha=2.5)
    probs_btts = calcular_prob_btts(casa, fora)

    # ── Seleciona probabilidade base pelo mercado ──────────────────
    if mercado == "1x2_casa":
        prob_base = probs_1x2["prob_casa"]
    elif mercado == "1x2_fora":
        prob_base = probs_1x2["prob_fora"]
    elif mercado == "over_2.5":
        prob_base = probs_ou["prob_over"]
    elif mercado == "under_2.5":
        prob_base = probs_ou["prob_under"]
    elif mercado == "btts_sim":
        prob_base = probs_btts["prob_btts_sim"]
    else:
        prob_base = probs_1x2["prob_casa"]

    # ── Blend de mercado + ajuste contextual avançado (com fallback) ──
    odd_oponente = dados.get("odd_oponente_mercado")
    p_no_vig = None
    try:
        p_no_vig = no_vig_probability(odd, odd_oponente)
    except Exception:
        p_no_vig = None

    source_quality = dados.get("source_quality", "fallback")
    market_features = build_market_features(
        odds_novid=p_no_vig,
        p_poisson=prob_base,
        odd_abertura=dados.get("odd_abertura"),
        odd_atual=odd,
        source_quality=source_quality,
    )

    prob_blend = blend_probability(
        p_poisson=prob_base,
        p_mercado=market_features.get("p_mercado_no_vig"),
        w=dados.get("blend_w_poisson"),
        liga=liga,
        mercado=mercado,
    )

    fator_total = _contextual_factor_avancado(dados)
    prob_ajustada = ajuste_contextual(prob_blend, fator_total)
    prob_calibrada = _predict_calibrated_probability(prob_ajustada, liga=liga, mercado=mercado)

    threshold_cfg = _obter_threshold_segmentado(liga, mercado)
    ev_floor = float(threshold_cfg.get("ev_floor", 0.04))

    # ── EV usando probabilidade calibrada ──────────────────────────
    ev = calcular_ev(prob_calibrada, odd)

    if ev < ev_floor:
        prob_implicita = round(1 / odd, 4)
        reasoning_trace = montar_reasoning_trace(
            mercado=mercado,
            odd=odd,
            prob_modelo=prob_calibrada,
            prob_implicita=prob_implicita,
            ev=ev,
            edge_score=0,
            confianca=dados.get("confianca_dados", 70),
            min_conf=threshold_cfg.get("confidence_floor", MIN_CONFIDENCE_ACTIONABLE),
        )
        reasoning_trace["prob_modelo_raw"] = round(prob_base, 4)
        reasoning_trace["prob_modelo_blend"] = round(prob_blend, 4)
        reasoning_trace["prob_modelo_ajustada"] = round(prob_ajustada, 4)
        reasoning_trace["prob_modelo_calibrada"] = round(prob_calibrada, 4)
        reasoning_trace["calibrator_fitted"] = _calibrator_is_fitted(PROB_CALIBRATOR)
        reasoning_trace["effective_halflife"] = probs_1x2.get("recency_halflife_usado")
        reasoning_trace["market_features"] = market_features
        reasoning_trace["segment_threshold"] = threshold_cfg
        result = {
            "prediction_id": prediction_id,
            "decisao": "DESCARTAR",
            "recomendacao_acao": "AVOID",
            "motivo": f"EV insuficiente: {ev*100:.2f}% (mínimo {ev_floor*100:.2f}%)",
            "jogo": dados["jogo"],
            "mercado": mercado,
            "odd": odd,
            "ev": ev,
            "ev_percentual": f"{ev*100:.2f}%",
            "edge_score": 0,
            "confidence_threshold": MIN_CONFIDENCE_ACTIONABLE,
            "reasoning_trace": reasoning_trace,
            "kelly_bruto_frac": 0.0,
            "kelly_bruto_pct": 0.0,
            "prob_modelo": prob_calibrada,
            "prob_modelo_raw": prob_base,
            "prob_modelo_blend": prob_blend,
            "prob_modelo_ajustada": prob_ajustada,
            "shadow_mode": bool(dados.get("shadow_mode", False)),
            "shadow_payload": {
                "prob_baseline": round(float(prob_base), 6),
                "prob_advanced": round(float(prob_calibrada), 6),
                "market_features": market_features,
                "segment_threshold": threshold_cfg,
            },
            # Dixon-Coles mesmo em descarte
            "rho_usado": probs_1x2["rho_usado"],
            "dc_delta_empate": probs_1x2["dc_delta_empate"],
        }
        # INTEGRATION: registra todos os jogos analisados (inclusive descartes).
        _registrar_pick(result, dados)
        return result

    # ── EDGE Score ─────────────────────────────────────────────────
    ev_score = ev_para_score(ev)
    edge_score = calcular_edge_score(
        ev_score,
        dados.get("confianca_dados", 70),
        dados.get("estabilidade_odd", 70),
        dados.get("contexto_jogo", 70),
    )

    decisao = decisao_sinal(edge_score)
    stake = calcular_stake(edge_score, dados.get("banca", 1000))
    recomendacao_acao = classificar_recomendacao(
        edge_score=edge_score,
        confianca=dados.get("confianca_dados", 70),
        ev=ev,
        min_conf=threshold_cfg.get("confidence_floor", MIN_CONFIDENCE_ACTIONABLE),
    )
    prob_implicita = round(1 / odd, 4)
    reasoning_trace = montar_reasoning_trace(
        mercado=mercado,
        odd=odd,
        prob_modelo=prob_calibrada,
        prob_implicita=prob_implicita,
        ev=ev,
        edge_score=edge_score,
        confianca=dados.get("confianca_dados", 70),
        min_conf=threshold_cfg.get("confidence_floor", MIN_CONFIDENCE_ACTIONABLE),
    )
    reasoning_trace["prob_modelo_raw"] = round(prob_base, 4)
    reasoning_trace["prob_modelo_blend"] = round(prob_blend, 4)
    reasoning_trace["prob_modelo_ajustada"] = round(prob_ajustada, 4)
    reasoning_trace["prob_modelo_calibrada"] = round(prob_calibrada, 4)
    reasoning_trace["calibrator_fitted"] = _calibrator_is_fitted(PROB_CALIBRATOR)
    reasoning_trace["effective_halflife"] = probs_1x2.get("recency_halflife_usado")
    reasoning_trace["market_features"] = market_features
    reasoning_trace["segment_threshold"] = threshold_cfg

    # Kelly também usa probabilidade calibrada.
    kelly_bruto_frac = calcular_kelly_fracionado(
        prob_modelo=prob_calibrada,
        odd=odd,
        fracao=0.25,
        teto=0.05,
    )

    # ── Log Dixon-Coles quando ajuste for relevante (>2%) ──────────
    if log_dc and abs(probs_1x2["dc_delta_empate"]) >= 2.0:
        jogo_nome = dados.get("jogo", "?")
        log_comparacao(jogo_nome, casa, fora, probs_1x2)

    result = {
        "prediction_id": prediction_id,
        # Campos originais
        "liga": dados["liga"],
        "jogo": dados["jogo"],
        "horario": dados.get("horario", ""),
        "mercado": mercado,
        "odd": odd,
        "prob_modelo_base": prob_base,
        "prob_modelo": prob_calibrada,
        "prob_modelo_raw": prob_base,
        "prob_modelo_blend": prob_blend,
        "prob_modelo_ajustada": prob_ajustada,
        "prob_implicita": prob_implicita,
        "ev": round(ev, 4),
        "ev_percentual": f"{ev*100:.2f}%",
        "edge_score": edge_score,
        "decisao": decisao,
        "recomendacao_acao": recomendacao_acao,
        "stake_unidades": stake["unidades"],
        "stake_reais": stake["valor_reais"],
        "unidade_reais": stake["unidade_valor"],
        "confidence_threshold": threshold_cfg.get("confidence_floor", MIN_CONFIDENCE_ACTIONABLE),
        "ev_floor": ev_floor,
        "edge_cutoff_segment": threshold_cfg.get("edge_cutoff", 65.0),
        "threshold_version": threshold_cfg.get("versao", "default"),
        "kelly_bruto_frac": kelly_bruto_frac,
        "kelly_bruto_pct": round(kelly_bruto_frac * 100, 2),
        "shadow_mode": bool(dados.get("shadow_mode", False)),
        "shadow_payload": {
            "prob_baseline": round(float(prob_base), 6),
            "prob_advanced": round(float(prob_calibrada), 6),
            "market_features": market_features,
            "segment_threshold": threshold_cfg,
        },
        "reasoning_trace": reasoning_trace,
        # Campos novos Dixon-Coles
        "prob_casa_raw": probs_1x2["prob_casa_raw"],
        "prob_empate_raw": probs_1x2["prob_empate_raw"],
        "prob_fora_raw": probs_1x2["prob_fora_raw"],
        "prob_casa_dc": probs_1x2["prob_casa"],
        "prob_empate_dc": probs_1x2["prob_empate"],
        "prob_fora_dc": probs_1x2["prob_fora"],
        "dc_delta_empate": probs_1x2["dc_delta_empate"],
        "rho_usado": probs_1x2["rho_usado"],
    }
    # INTEGRATION: registra todos os jogos analisados (BET/SKIP/AVOID).
    _registrar_pick(result, dados)
    return result


def formatar_sinal(analise):
    """
    Formata a análise como mensagem para o Telegram.
    """
    if analise["decisao"] == "DESCARTAR":
        return None

    emoji_decisao = "⚡" if analise["decisao"] == "PREMIUM" else "✅"

    mercados_legivel = {
        "1x2_casa": "Vitória do time da casa",
        "1x2_fora": "Vitória do time visitante",
        "over_2.5": "Mais de 2.5 gols na partida",
        "under_2.5": "Menos de 2.5 gols na partida",
        "btts_sim": "Ambas as equipes marcam",
        "btts_nao": "Pelo menos um time não marca",
    }
    mercado_texto = mercados_legivel.get(analise["mercado"], analise["mercado"])

    horario_raw = analise.get("horario", "")
    try:
        from datetime import datetime, timedelta

        dt = datetime.strptime(horario_raw, "%Y-%m-%dT%H:%M:%SZ")
        dt_brasil = dt - timedelta(hours=3)
        horario_formatado = dt_brasil.strftime("%d/%m/%Y — %H:%M")
    except Exception:
        horario_formatado = horario_raw

    msg = (
        f"{emoji_decisao} SINAL EDGE PROTOCOL\n\n"
        f"🏆 {analise['liga']}\n"
        f"⚽ {analise['jogo']}\n"
        f"📅 {horario_formatado}\n\n"
        f"📌 Aposta: {mercado_texto}\n"
        f"💰 Odd: {analise['odd']}\n"
        f"📊 EDGE Score: {analise['edge_score']}/100\n"
        f"🎯 EV: {analise['ev_percentual']}\n\n"
        f"🏦 Stake: {analise['stake_unidades']} unidades"
        f" = R${analise['stake_reais']:.2f}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    return msg


if __name__ == "__main__":
    print("=== SIMULAÇÃO DE ANÁLISE + DIXON-COLES ===\n")

    jogo_teste = {
        "liga": "Premier League",
        "jogo": "Arsenal vs Chelsea",
        "horario": "17h30",
        "media_gols_casa": 2.1,
        "media_gols_fora": 1.0,
        "mercado": "1x2_casa",
        "odd": 1.92,
        "ajuste_lesoes": -0.03,
        "ajuste_motivacao": 0.02,
        "ajuste_fadiga": 0.0,
        "confianca_dados": 85,
        "estabilidade_odd": 80,
        "contexto_jogo": 75,
        "banca": 1000,
    }

    resultado = analisar_jogo(jogo_teste)

    print(f"Jogo:        {resultado['jogo']}")
    print(f"Liga:        {resultado['liga']} (ρ={resultado['rho_usado']})")
    print(f"Mercado:     {resultado['mercado']}")
    print(f"Odd:         {resultado['odd']}")
    print(f"Prob modelo: {resultado['prob_modelo']*100:.1f}%")
    print(f"EV:          {resultado['ev_percentual']}")
    print(f"EDGE Score:  {resultado['edge_score']}/100")
    print(f"Decisão:     {resultado['decisao']}")
    print(f"Stake:       {resultado['stake_unidades']}u = R${resultado['stake_reais']:.2f}")
    print("\nDixon-Coles:")
    print(f"  Casa:   {resultado['prob_casa_raw']*100:.1f}% → {resultado['prob_casa_dc']*100:.1f}%")
    print(
        f"  Empate: {resultado['prob_empate_raw']*100:.1f}% → "
        f"{resultado['prob_empate_dc']*100:.1f}%  (Δ{resultado['dc_delta_empate']:+.2f}%)"
    )
    print(f"  Fora:   {resultado['prob_fora_raw']*100:.1f}% → {resultado['prob_fora_dc']*100:.1f}%")

    print("\n--- MENSAGEM FORMATADA ---\n")
    msg = formatar_sinal(resultado)
    if msg:
        print(msg)

    # Teste com Serie A (rho mais negativo)
    print("\n=== TESTE SERIE A (ρ=-0.13) ===\n")
    jogo_italy = {**jogo_teste, "liga": "Serie A", "jogo": "AC Milan vs Inter"}
    r2 = analisar_jogo(jogo_italy)
    print(f"ρ usado: {r2['rho_usado']}")
    print(
        f"Empate: {r2['prob_empate_raw']*100:.1f}% → "
        f"{r2['prob_empate_dc']*100:.1f}%  (Δ{r2['dc_delta_empate']:+.2f}%)"
    )
