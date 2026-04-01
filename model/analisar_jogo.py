import os
import uuid

from poisson import (
    calcular_probabilidades,
    calcular_prob_over_under,
    calcular_prob_btts,
    ajuste_contextual,
    log_comparacao,
)
from edge_score import (
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
from calibrator import BucketCalibrator
from picks_log import PickLogger


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
            return BucketCalibrator.load(CALIBRACAO_PROB_PATH)
        except Exception:
            # Fallback seguro: pass-through caso arquivo exista mas esteja inválido.
            return BucketCalibrator()
    return BucketCalibrator()


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
    except Exception:
        # Falha de log nao deve quebrar ciclo principal de decisao.
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

    # ── Ajuste contextual (lesões, motivação, fadiga) ──────────────
    fator_total = (
        dados.get("ajuste_lesoes", 0)
        + dados.get("ajuste_motivacao", 0)
        + dados.get("ajuste_fadiga", 0)
    )
    prob_ajustada = ajuste_contextual(prob_base, fator_total)
    prob_calibrada = PROB_CALIBRATOR.predict(prob_ajustada)

    # ── EV usando probabilidade calibrada ──────────────────────────
    ev = calcular_ev(prob_calibrada, odd)

    if ev < 0.04:
        prob_implicita = round(1 / odd, 4)
        reasoning_trace = montar_reasoning_trace(
            mercado=mercado,
            odd=odd,
            prob_modelo=prob_calibrada,
            prob_implicita=prob_implicita,
            ev=ev,
            edge_score=0,
            confianca=dados.get("confianca_dados", 70),
            min_conf=MIN_CONFIDENCE_ACTIONABLE,
        )
        reasoning_trace["prob_modelo_raw"] = round(prob_ajustada, 4)
        reasoning_trace["prob_modelo_calibrada"] = round(prob_calibrada, 4)
        reasoning_trace["calibrator_fitted"] = bool(getattr(PROB_CALIBRATOR, "is_fitted", False))
        reasoning_trace["effective_halflife"] = probs_1x2.get("recency_halflife_usado")
        result = {
            "prediction_id": prediction_id,
            "decisao": "DESCARTAR",
            "recomendacao_acao": "AVOID",
            "motivo": f"EV insuficiente: {ev*100:.2f}% (mínimo 4%)",
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
            "prob_modelo_raw": prob_ajustada,
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
        min_conf=MIN_CONFIDENCE_ACTIONABLE,
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
        min_conf=MIN_CONFIDENCE_ACTIONABLE,
    )
    reasoning_trace["prob_modelo_raw"] = round(prob_ajustada, 4)
    reasoning_trace["prob_modelo_calibrada"] = round(prob_calibrada, 4)
    reasoning_trace["calibrator_fitted"] = bool(getattr(PROB_CALIBRATOR, "is_fitted", False))
    reasoning_trace["effective_halflife"] = probs_1x2.get("recency_halflife_usado")

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
        "prob_modelo_raw": prob_ajustada,
        "prob_implicita": prob_implicita,
        "ev": round(ev, 4),
        "ev_percentual": f"{ev*100:.2f}%",
        "edge_score": edge_score,
        "decisao": decisao,
        "recomendacao_acao": recomendacao_acao,
        "stake_unidades": stake["unidades"],
        "stake_reais": stake["valor_reais"],
        "unidade_reais": stake["unidade_valor"],
        "confidence_threshold": MIN_CONFIDENCE_ACTIONABLE,
        "kelly_bruto_frac": kelly_bruto_frac,
        "kelly_bruto_pct": round(kelly_bruto_frac * 100, 2),
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
