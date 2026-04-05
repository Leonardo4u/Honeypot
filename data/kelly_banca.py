import sqlite3
import json
import os
import math
import logging
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
BANCA_PATH = os.path.join(os.path.dirname(__file__), "banca_estado.json")

BANCA_INICIAL = 1000.0
KELLY_FRACAO = 0.25
TETO_MAXIMO = 0.03
PISO_MINIMO = 0.005
DRAWDOWN_ALERTA = 0.20
logger = logging.getLogger(__name__)

TIER_MULTIPLICADOR = {
    "padrao":  0.8,
    "premium": 1.0,
    "elite":   1.2
}


def fator_reducao_correlacao_mesmo_jogo(sinais_mesmo_jogo_abertos):
    if sinais_mesmo_jogo_abertos <= 0:
        return 1.0
    if sinais_mesmo_jogo_abertos == 1:
        return 0.80
    if sinais_mesmo_jogo_abertos == 2:
        return 0.65
    return 0.50

def criar_tabela_banca():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS banca_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            banca_valor REAL,
            banca_maxima REAL,
            drawdown_percentual REAL,
            roi_acumulado REAL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def carregar_estado_banca():
    if not os.path.exists(BANCA_PATH):
        estado = {
            "banca_atual": BANCA_INICIAL,
            "banca_inicial": BANCA_INICIAL,
            "banca_maxima": BANCA_INICIAL,
            "ultima_atualizacao": str(date.today())
        }
        salvar_estado_banca(estado)
        return estado

    with open(BANCA_PATH, "r") as f:
        return json.load(f)

def salvar_estado_banca(estado):
    with open(BANCA_PATH, "w") as f:
        json.dump(estado, f, indent=2)

def atualizar_banca(lucro_unidades):
    estado = carregar_estado_banca()
    unidade = estado["banca_atual"] * 0.01
    lucro_reais = lucro_unidades * unidade

    estado["banca_atual"] = round(estado["banca_atual"] + lucro_reais, 2)
    estado["banca_maxima"] = max(estado["banca_maxima"], estado["banca_atual"])
    estado["ultima_atualizacao"] = str(date.today())

    drawdown = (estado["banca_maxima"] - estado["banca_atual"]) / estado["banca_maxima"]
    if drawdown >= DRAWDOWN_ALERTA:
        logger.warning("Drawdown de %.1f%% atingido", drawdown * 100)
        logger.warning("Banca maxima: R$%.2f", estado["banca_maxima"])
        logger.warning("Banca atual: R$%.2f", estado["banca_atual"])

    salvar_estado_banca(estado)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    roi = (estado["banca_atual"] - estado["banca_inicial"]) / estado["banca_inicial"] * 100
    c.execute('''
        INSERT INTO banca_historico (data, banca_valor, banca_maxima, drawdown_percentual, roi_acumulado)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(date.today()), estado["banca_atual"], estado["banca_maxima"],
          round(drawdown * 100, 2), round(roi, 2)))
    conn.commit()
    conn.close()

    return estado

def calcular_kelly(
    prob_modelo,
    odd,
    edge_score,
    sinais_abertos=0,
    liga=None,
    sinais_liga_hoje=0,
    sinais_mesmo_jogo_abertos=0,
):
    """
    Calcula stake via Kelly fracionado com todas as regras de segurana.
    Retorna dict com stake em % e em reais.
    """
    try:
        prob_modelo = float(prob_modelo)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_prob_modelo"}

    try:
        odd = float(odd)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_odd"}

    try:
        edge_score = float(edge_score)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_edge_score"}

    try:
        sinais_abertos = int(sinais_abertos)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_sinais_abertos"}

    try:
        sinais_liga_hoje = int(sinais_liga_hoje)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_sinais_liga_hoje"}

    try:
        sinais_mesmo_jogo_abertos = int(sinais_mesmo_jogo_abertos)
    except (TypeError, ValueError):
        return {"aprovado": False, "motivo": "invalid_sinais_mesmo_jogo"}

    if not math.isfinite(prob_modelo) or prob_modelo < 0 or prob_modelo > 1:
        return {"aprovado": False, "motivo": "invalid_prob_modelo_range"}
    if not math.isfinite(odd) or odd <= 1:
        return {"aprovado": False, "motivo": "invalid_odd_range"}
    if not math.isfinite(edge_score):
        return {"aprovado": False, "motivo": "invalid_edge_score_range"}
    if sinais_abertos < 0 or sinais_liga_hoje < 0 or sinais_mesmo_jogo_abertos < 0:
        return {"aprovado": False, "motivo": "invalid_signal_counts"}

    estado = carregar_estado_banca()
    banca = estado["banca_atual"]

    kelly_completo = (prob_modelo * odd - 1) / (odd - 1)

    if kelly_completo <= 0:
        return {"aprovado": False, "motivo": "Kelly negativo  sem edge real"}

    kelly_fracionado = kelly_completo * KELLY_FRACAO

    if edge_score >= 90:
        tier = "elite"
    elif edge_score >= 80:
        tier = "premium"
    else:
        tier = "padrao"

    multiplicador = TIER_MULTIPLICADOR[tier]
    kelly_ajustado = kelly_fracionado * multiplicador

    if sinais_abertos >= 3:
        kelly_ajustado *= 0.80
        print(f"  Redução 20%: {sinais_abertos} apostas abertas")

    fator_correlacao = fator_reducao_correlacao_mesmo_jogo(sinais_mesmo_jogo_abertos)
    kelly_ajustado *= fator_correlacao

    if sinais_liga_hoje >= 2:
        return {"aprovado": False, "motivo": f"Limite de 2 apostas da mesma liga atingido"}

    exposicao_atual = calcular_exposicao_atual()
    if exposicao_atual + kelly_ajustado > 0.15:
        kelly_ajustado = max(0, 0.15 - exposicao_atual)
        if kelly_ajustado < PISO_MINIMO:
            return {"aprovado": False, "motivo": "Exposio mxima de 15% atingida"}

    kelly_ajustado = min(kelly_ajustado, TETO_MAXIMO)

    if not math.isfinite(kelly_ajustado) or kelly_ajustado < 0:
        return {"aprovado": False, "motivo": "invalid_kelly_output"}

    if kelly_ajustado < PISO_MINIMO:
        return {
            "aprovado": False,
            "motivo": f"Kelly {kelly_ajustado*100:.2f}% abaixo do mínimo de {PISO_MINIMO*100:.1f}%"
        }

    valor_reais = round(banca * kelly_ajustado, 2)
    if not math.isfinite(valor_reais) or valor_reais < 0:
        return {"aprovado": False, "motivo": "invalid_stake_value"}

    return {
        "aprovado": True,
        "tier": tier,
        "kelly_completo_pct": round(kelly_completo * 100, 2),
        "kelly_fracionado_pct": round(kelly_fracionado * 100, 2),
        "kelly_final_pct": round(kelly_ajustado * 100, 2),
        "valor_reais": valor_reais,
        "banca_atual": banca,
        "multiplicador": multiplicador,
        "fator_correlacao_mesmo_jogo": fator_correlacao,
    }

def calcular_exposicao_atual():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT stake_unidades FROM sinais
        WHERE status = 'pendente' AND data = ?
    ''', (str(date.today()),))
    stakes = c.fetchall()
    conn.close()

    total = sum(s[0] * 0.01 for s in stakes if s[0])
    return total

def contar_sinais_abertos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM sinais
        WHERE status = 'pendente' AND data = ?
    ''', (str(date.today()),))
    count = c.fetchone()[0]
    conn.close()
    return count

def contar_sinais_liga_hoje(liga):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM sinais
        WHERE liga = ? AND data = ? AND status != 'descartado'
    ''', (liga, str(date.today())))
    count = c.fetchone()[0]
    conn.close()
    return count


def contar_sinais_mesmo_jogo_abertos(jogo):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        SELECT COUNT(*) FROM sinais
        WHERE jogo = ? AND data = ? AND status = 'pendente'
    ''',
        (jogo, str(date.today())),
    )
    count = c.fetchone()[0]
    conn.close()
    return count

def gerar_relatorio_diario():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    hoje = str(date.today())
    c.execute('''
        SELECT jogo, mercado, odd, resultado, lucro_unidades, edge_score
        FROM sinais WHERE data = ?
    ''', (hoje,))
    apostas_hoje = c.fetchall()

    c.execute('''
        SELECT lucro_unidades FROM sinais
        WHERE status = 'finalizado' AND lucro_unidades IS NOT NULL
        ORDER BY criado_em ASC
    ''')
    todos_lucros = [r[0] for r in c.fetchall()]

    trinta_dias = str(date.today() - timedelta(days=30))
    c.execute('''
        SELECT SUM(lucro_unidades) FROM sinais
        WHERE status = 'finalizado'
        AND data >= ? AND lucro_unidades IS NOT NULL
    ''', (trinta_dias,))
    lucro_30d = c.fetchone()[0] or 0

    conn.close()

    estado = carregar_estado_banca()
    banca = estado["banca_atual"]
    banca_inicial = estado["banca_inicial"]
    banca_maxima = estado["banca_maxima"]
    roi_acumulado = (banca - banca_inicial) / banca_inicial * 100
    unidade = banca * 0.01
    roi_30d = lucro_30d * unidade / banca_inicial * 100

    max_wins = max_losses = wins_atual = losses_atual = 0
    for lucro in todos_lucros:
        if lucro > 0:
            wins_atual += 1
            losses_atual = 0
            max_wins = max(max_wins, wins_atual)
        else:
            losses_atual += 1
            wins_atual = 0
            max_losses = max(max_losses, losses_atual)

    drawdown = (banca_maxima - banca) / banca_maxima * 100 if banca_maxima > 0 else 0

    relatorio = {
        "data": hoje,
        "banca": {
            "atual": banca,
            "inicial": banca_inicial,
            "maxima": banca_maxima,
            "drawdown_atual_pct": round(drawdown, 2)
        },
        "performance": {
            "roi_acumulado_pct": round(roi_acumulado, 2),
            "roi_30_dias_pct": round(roi_30d, 2),
            "maior_sequencia_wins": max_wins,
            "maior_sequencia_losses": max_losses
        },
        "apostas_hoje": [
            {
                "jogo": a[0],
                "mercado": a[1],
                "odd": a[2],
                "resultado": a[3] or "pendente",
                "lucro_unidades": a[4],
                "edge_score": a[5]
            }
            for a in apostas_hoje
        ],
        "total_apostas_hoje": len(apostas_hoje)
    }

    path = os.path.join(os.path.dirname(__file__), "..", "logs", f"relatorio_{hoje}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    return relatorio

def imprimir_relatorio(relatorio):
    b = relatorio["banca"]
    p = relatorio["performance"]

    print("\n" + "="*50)
    print(f"  RELATÓRIO DIÁRIO — {relatorio['data']}")
    print("="*50)
    print(f"\n💰 BANCA")
    print(f"  Atual:    R${b['atual']:.2f}")
    print(f"  Inicial:  R${b['inicial']:.2f}")
    print(f"  Máxima:   R${b['maxima']:.2f}")
    print(f"  Drawdown: {b['drawdown_atual_pct']:.1f}%")
    print(f"\n📈 PERFORMANCE")
    print(f"  ROI Acumulado:  {p['roi_acumulado_pct']:+.2f}%")
    print(f"  ROI 30 dias:    {p['roi_30_dias_pct']:+.2f}%")
    print(f"  Maior sequência wins:   {p['maior_sequencia_wins']}")
    print(f"  Maior sequência losses: {p['maior_sequencia_losses']}")
    print(f"\n📋 APOSTAS HOJE ({relatorio['total_apostas_hoje']})")
    for a in relatorio["apostas_hoje"]:
        emoji = "[OK]" if a["resultado"] == "verde" else "[ERRO]" if a["resultado"] == "vermelho" else ""
        lucro = f"{a['lucro_unidades']:+.2f}u" if a["lucro_unidades"] else "-"
        print(f"  {emoji} {a['jogo']} | {a['mercado']} @ {a['odd']} | {lucro}")
    print("="*50)

if __name__ == "__main__":
    criar_tabela_banca()
    print("Sistema Kelly iniciado.")
    print(f"Banca atual: R${carregar_estado_banca()['banca_atual']:.2f}")

    print("\nTeste de clculo Kelly:")
    resultado = calcular_kelly(
        prob_modelo=0.60,
        odd=1.92,
        edge_score=85,
        sinais_abertos=1,
        liga="EPL",
        sinais_liga_hoje=0
    )
    if resultado["aprovado"]:
        print(f"  Tier: {resultado['tier']}")
        print(f"  Kelly completo: {resultado['kelly_completo_pct']}%")
        print(f"  Kelly fracionado: {resultado['kelly_fracionado_pct']}%")
        print(f"  Kelly final: {resultado['kelly_final_pct']}%")
        print(f"  Valor: R${resultado['valor_reais']:.2f}")
    else:
        print(f"  Bloqueado: {resultado['motivo']}")