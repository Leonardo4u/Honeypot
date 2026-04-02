import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CANAL_FREE = os.getenv("CANAL_FREE")
CANAL_VIP = os.getenv("CANAL_VIP")

from data.database import buscar_sinais_hoje, resumo_mensal, atualizar_resultado

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ Edge Protocol ativo!\n\n"
        "Comandos disponíveis:\n"
        "/hoje — Sinais do dia\n"
        "/banca — Estado da banca\n"
        "/historico — Resumo do mês\n"
        "/resultado — Registrar resultado\n"
        "/ajuda — Como usar o sistema"
    )

async def hoje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sinais = buscar_sinais_hoje()
    if not sinais:
        await update.message.reply_text("📋 Nenhum sinal enviado hoje ainda.")
        return

    msg = f"📋 SINAIS DE HOJE ({len(sinais)})\n\n"
    for s in sinais:
        status_emoji = "⏳" if s[10] == "pendente" else ("✅" if s[11] == "verde" else "❌")
        msg += f"{status_emoji} {s[3]} | {s[4]}\n"
        msg += f"   Odd: {s[5]} | Score: {s[7]}/100\n"
        msg += f"   Stake: {s[8]}u | Status: {s[10]}\n\n"

    await update.message.reply_text(msg)

async def banca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resumo = resumo_mensal()
    total = resumo[0] or 0
    vitorias = resumo[1] or 0
    derrotas = resumo[2] or 0
    lucro = resumo[3] or 0.0

    win_rate = (vitorias / total * 100) if total > 0 else 0
    banca_inicial = 1000
    unidade = banca_inicial * 0.01
    banca_atual = banca_inicial + (lucro * unidade)
    roi = ((banca_atual - banca_inicial) / banca_inicial) * 100

    if roi >= 0:
        roi_emoji = "📈"
    else:
        roi_emoji = "📉"

    msg = (
        f"🏦 ESTADO DA BANCA\n\n"
        f"Banca inicial:  R${banca_inicial:.2f}\n"
        f"Banca atual:    R${banca_atual:.2f}\n"
        f"{roi_emoji} ROI:          {roi:.1f}%\n\n"
        f"📊 Performance:\n"
        f"Total sinais:  {total}\n"
        f"Vitórias:      {vitorias}\n"
        f"Derrotas:      {derrotas}\n"
        f"Win Rate:      {win_rate:.0f}%\n"
        f"Lucro:         {lucro:.1f} unidades\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    await update.message.reply_text(msg)

async def historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resumo = resumo_mensal()
    total = resumo[0] or 0
    vitorias = resumo[1] or 0
    derrotas = resumo[2] or 0
    lucro = resumo[3] or 0.0

    win_rate = (vitorias / total * 100) if total > 0 else 0
    pendentes = total - vitorias - derrotas

    msg = (
        f"📈 HISTÓRICO DO MÊS\n\n"
        f"✅ Vitórias:   {vitorias}\n"
        f"❌ Derrotas:   {derrotas}\n"
        f"⏳ Pendentes:  {pendentes}\n"
        f"📊 Win Rate:   {win_rate:.0f}%\n"
        f"💰 Lucro:      {lucro:.1f} unidades\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    await update.message.reply_text(msg)

async def resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /resultado <id> <verde|vermelho> <odd>
    Exemplo: /resultado 1 verde 1.92
    """
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "Uso correto:\n"
            "/resultado <id> <verde|vermelho> <odd>\n\n"
            "Exemplo:\n"
            "/resultado 1 verde 1.92"
        )
        return

    try:
        sinal_id = int(args[0])
        resultado_str = args[1].lower()
        odd = float(args[2])

        if resultado_str not in ["verde", "vermelho"]:
            await update.message.reply_text("Resultado deve ser: verde ou vermelho")
            return

        if resultado_str == "verde":
            lucro = odd - 1
        else:
            lucro = -1.0

        atualizar_resultado(sinal_id, resultado_str, lucro)

        emoji = "✅" if resultado_str == "verde" else "❌"
        msg = (
            f"{emoji} Resultado registrado!\n\n"
            f"Sinal ID: #{sinal_id}\n"
            f"Resultado: {resultado_str.upper()}\n"
            f"Odd: {odd}\n"
            f"Lucro: {lucro:+.2f} unidades\n\n"
            f"Use /banca para ver o estado atualizado."
        )
        await update.message.reply_text(msg)

    except ValueError:
        await update.message.reply_text("ID e odd devem ser números.\nExemplo: /resultado 1 verde 1.92")

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 COMO USAR O EDGE PROTOCOL\n\n"
        "1. O sistema analisa jogos automaticamente\n"
        "   às 08h, 13h e 17h todos os dias.\n\n"
        "2. Quando um sinal for aprovado, ele aparece\n"
        "   automaticamente no canal VIP.\n\n"
        "3. Após o jogo, registre o resultado:\n"
        "   /resultado <id> <verde|vermelho> <odd>\n\n"
        "4. Acompanhe sua banca com /banca\n\n"
        "⚠️ Nunca aposte mais do que o indicado.\n"
        "Siga sempre a gestão de banca.\n\n"
        "━━━━━━━━━━━━━━━\n"
        "⚡ Edge Protocol"
    )
    await update.message.reply_text(msg)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hoje", hoje))
    app.add_handler(CommandHandler("banca", banca))
    app.add_handler(CommandHandler("historico", historico))
    app.add_handler(CommandHandler("resultado", resultado))
    app.add_handler(CommandHandler("ajuda", ajuda))
    print("Bot rodando...")
    app.run_polling()