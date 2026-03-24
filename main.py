import os
import sys
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "model"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "data"))

from analisar_jogo import analisar_jogo, formatar_sinal
from database import inserir_sinal, buscar_sinais_hoje, resumo_mensal

TOKEN = os.getenv("BOT_TOKEN")
CANAL_FREE = os.getenv("CANAL_FREE")
CANAL_VIP = os.getenv("CANAL_VIP")

async def enviar_sinal(jogo_dados, publicar_free=False):
    """
    Analisa um jogo e envia o sinal para os canais se aprovado.
    """
    bot = Bot(token=TOKEN)
    analise = analisar_jogo(jogo_dados)

    if analise["decisao"] == "DESCARTAR":
        print(f"DESCARTADO: {analise['jogo']} — {analise['motivo']}")
        return None

    msg = formatar_sinal(analise)
    if not msg:
        return None

    print(f"\nEnviando sinal: {analise['jogo']}")
    print(f"EDGE Score: {analise['edge_score']} | Decisão: {analise['decisao']}")

    await bot.send_message(chat_id=CANAL_VIP, text=msg)
    print("Enviado para canal VIP.")

    if publicar_free:
        await bot.send_message(chat_id=CANAL_FREE, text=msg)
        print("Enviado para canal Free.")

    sinal_id = inserir_sinal(
        liga=analise["liga"],
        jogo=analise["jogo"],
        mercado=analise["mercado"],
        odd=analise["odd"],
        ev=analise["ev"],
        score=analise["edge_score"],
        stake=analise["stake_unidades"]
    )
    print(f"Sinal salvo no banco. ID: {sinal_id}")
    return sinal_id

async def enviar_resultado(sinal_id, resultado, odd_final):
    """
    Envia o resultado de um sinal para os canais.
    resultado: 'verde' ou 'vermelho'
    """
    from database import atualizar_resultado
    bot = Bot(token=TOKEN)

    if resultado == "verde":
        emoji = "✅"
        texto_resultado = "VERDE"
    else:
        emoji = "❌"
        texto_resultado = "VERMELHO"

    resumo = resumo_mensal()
    total = resumo[0] or 0
    vitorias = resumo[1] or 0
    derrotas = resumo[2] or 0
    lucro = resumo[3] or 0

    win_rate = (vitorias / total * 100) if total > 0 else 0

    msg = (
        f"{emoji} RESULTADO — SINAL #{sinal_id}\n\n"
        f"Resultado: {texto_resultado}\n\n"
        f"📊 Histórico do mês:\n"
        f"Record: {vitorias}V / {derrotas}D\n"
        f"Win Rate: {win_rate:.0f}%\n"
        f"Lucro total: {lucro:.1f}u\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )

    await bot.send_message(chat_id=CANAL_VIP, text=msg)
    await bot.send_message(chat_id=CANAL_FREE, text=msg)

    lucro_unidades = (odd_final - 1) if resultado == "verde" else -1
    atualizar_resultado(sinal_id, resultado, lucro_unidades)
    print(f"Resultado registrado. Sinal #{sinal_id}: {texto_resultado}")

async def teste_completo():
    """
    Simula o fluxo completo: analisa, envia sinal e registra resultado.
    """
    print("=== TESTE COMPLETO DO SISTEMA ===\n")

    jogo = {
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
        "banca": 1000
    }

    sinal_id = await enviar_sinal(jogo, publicar_free=False)

    if sinal_id:
        print("\nSinal enviado com sucesso!")
        print(f"ID no banco: {sinal_id}")
        print("\nPara registrar resultado use:")
        print(f"await enviar_resultado({sinal_id}, 'verde', 1.92)")

if __name__ == "__main__":
    asyncio.run(teste_completo())