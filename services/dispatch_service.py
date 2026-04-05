from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from telegram import Bot


def formatar_pick(
    analise: Dict[str, Any],
    kelly: Dict[str, Any],
    carregar_estado_banca_fn: Callable[[], Dict[str, Any]],
) -> Optional[str]:
    """Formata a mensagem de pick para envio no Telegram."""
    if analise["decisao"] == "DESCARTAR":
        return None

    emoji_tier = {"elite": "", "premium": "", "padrao": "[OK]"}
    emoji = emoji_tier.get(kelly["tier"], "[OK]")

    mercados_legivel = {
        "1x2_casa": "Vitoria do time da casa",
        "1x2_fora": "Vitoria do time visitante",
        "over_2.5": "Mais de 2.5 gols na partida",
        "under_2.5": "Menos de 2.5 gols na partida",
    }
    mercado_texto = mercados_legivel.get(analise["mercado"], analise["mercado"])

    horario_raw = analise.get("horario", "")
    try:
        dt = datetime.strptime(horario_raw, "%Y-%m-%dT%H:%M:%SZ")
        dt_brasil = dt - timedelta(hours=3)
        horario_formatado = dt_brasil.strftime("%d/%m/%Y - %H:%M")
    except Exception:
        horario_formatado = horario_raw

    estado = carregar_estado_banca_fn()
    banca_atual = estado["banca_atual"]

    steam_linha = ""
    if analise.get("steam_bonus", 0) > 0:
        steam_linha = f"🔥 Steam: +{analise['steam_bonus']}pts (sharp money)\n"

    sos_linha = ""
    if "+SOS" in analise.get("fonte_dados", ""):
        sos_linha = " SOS: forca do adversario ajustada\n"

    return (
        f"{emoji} SINAL EDGE PROTOCOL - {kelly['tier'].upper()}\n\n"
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


def formatar_resumo_diario(payload: Dict[str, Any]) -> str:
    """Formata mensagem textual de resumo diario."""
    total = payload["total"]
    vitorias = payload["vitorias"]
    derrotas = payload["derrotas"]
    lucro = payload["lucro"]
    win_rate = payload["win_rate"]
    banca = payload["banca"]
    roi = payload["roi"]
    drawdown = payload["drawdown"]

    return (
        f"📊 RESUMO DO DIA\n\n"
        f"Sinais: {total} | ✅ {vitorias} | ❌ {derrotas}\n"
        f"Win Rate: {win_rate:.0f}%\n"
        f"Lucro: {lucro:+.1f} unidades\n\n"
        f"💰 Banca: R${banca:.2f}\n"
        f"📈 ROI: {roi:+.2f}%\n"
        f"📉 Drawdown: {drawdown:.1f}%\n"
        f"{payload.get('clv_linha', '')}"
        f"{payload.get('brier_linha', '')}"
        f"{payload.get('calibracao_linha', '')}"
        f"\n━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )


async def enviar_resumo(resumo: str, token: Optional[str], canal_vip: Optional[str], canal_free: Optional[str]) -> None:
    """Envia resumo diario para canais VIP e FREE."""
    if not token or not canal_vip or not canal_free:
        return
    bot = Bot(token=token)
    await bot.send_message(chat_id=canal_vip, text=resumo)
    await bot.send_message(chat_id=canal_free, text=resumo)
