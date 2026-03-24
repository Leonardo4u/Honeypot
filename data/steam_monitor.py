import sqlite3
import requests
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"

def criar_tabelas_steam():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jogo TEXT NOT NULL,
            mercado TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            odd_pinnacle REAL,
            odd_media REAL,
            odd_max REAL,
            odd_min REAL,
            casas_json TEXT,
            tipo TEXT DEFAULT 'snapshot'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS steam_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinal_id INTEGER,
            jogo TEXT NOT NULL,
            mercado TEXT NOT NULL,
            odd_abertura REAL,
            odd_atual REAL,
            steam_magnitude REAL,
            steam_velocidade REAL,
            steam_consenso REAL,
            pinnacle_lidera INTEGER DEFAULT 0,
            tipo TEXT,
            timestamp TEXT,
            pontos_bonus INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    print("Tabelas steam criadas.")

def buscar_odds_todas_casas(liga_key, jogo_home, jogo_away, mercado):
    """
    Busca odds de todas as casas disponíveis para um jogo específico.
    """
    if not API_KEY:
        return None

    url = f"{BASE_URL}/sports/{liga_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        jogos = response.json()
        for j in jogos:
            h = j.get("home_team", "").lower()
            a = j.get("away_team", "").lower()

            if jogo_home.lower() in h and jogo_away.lower() in a:
                odds_por_casa = {}
                odd_pinnacle = None

                for bm in j.get("bookmakers", []):
                    for market in bm.get("markets", []):
                        odd_valor = None

                        if mercado == "1x2_casa" and market["key"] == "h2h":
                            for o in market["outcomes"]:
                                if o["name"] == j["home_team"]:
                                    odd_valor = o["price"]

                        elif mercado == "over_2.5" and market["key"] == "totals":
                            for o in market["outcomes"]:
                                if o["name"] == "Over":
                                    odd_valor = o["price"]

                        if odd_valor:
                            odds_por_casa[bm["key"]] = odd_valor
                            if bm["key"] == "pinnacle":
                                odd_pinnacle = odd_valor

                if odds_por_casa:
                    valores = list(odds_por_casa.values())
                    return {
                        "odd_pinnacle": odd_pinnacle,
                        "odd_media": round(sum(valores) / len(valores), 3),
                        "odd_max": max(valores),
                        "odd_min": min(valores),
                        "casas": odds_por_casa,
                        "total_casas": len(odds_por_casa)
                    }

        return None

    except Exception as e:
        print(f"Erro ao buscar odds: {e}")
        return None

def salvar_snapshot(jogo, mercado, dados_odds, tipo="snapshot"):
    """
    Salva snapshot das odds no banco.
    """
    if not dados_odds:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO odds_snapshots
        (jogo, mercado, timestamp, odd_pinnacle, odd_media, odd_max, odd_min, casas_json, tipo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        jogo, mercado,
        datetime.now(timezone.utc).isoformat(),
        dados_odds.get("odd_pinnacle"),
        dados_odds["odd_media"],
        dados_odds["odd_max"],
        dados_odds["odd_min"],
        json.dumps(dados_odds["casas"]),
        tipo
    ))
    conn.commit()
    conn.close()

def buscar_snapshot_abertura(jogo, mercado):
    """
    Busca o primeiro snapshot salvo (abertura) de um jogo.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT odd_pinnacle, odd_media, odd_max, odd_min, casas_json, timestamp
        FROM odds_snapshots
        WHERE jogo = ? AND mercado = ? AND tipo = 'abertura'
        ORDER BY timestamp ASC
        LIMIT 1
    ''', (jogo, mercado))
    row = c.fetchone()
    conn.close()
    return row

def buscar_snapshots_recentes(jogo, mercado, horas=2):
    """
    Busca snapshots das últimas N horas para calcular velocidade.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    c.execute('''
        SELECT odd_pinnacle, odd_media, casas_json, timestamp
        FROM odds_snapshots
        WHERE jogo = ? AND mercado = ? AND timestamp >= ?
        ORDER BY timestamp ASC
    ''', (jogo, mercado, limite))
    rows = c.fetchall()
    conn.close()
    return rows

def calcular_steam(jogo, mercado, dados_atuais):
    """
    Calcula steam positivo comparando com snapshot de abertura.
    """
    abertura = buscar_snapshot_abertura(jogo, mercado)
    if not abertura:
        return None

    odd_abertura = abertura[0] or abertura[1]
    odd_atual = dados_atuais.get("odd_pinnacle") or dados_atuais["odd_media"]

    if not odd_abertura or not odd_atual:
        return None

    magnitude = round((odd_atual - odd_abertura) / odd_abertura * 100, 2)

    snapshots_recentes = buscar_snapshots_recentes(jogo, mercado, horas=2)
    velocidade = 0
    if len(snapshots_recentes) >= 2:
        odd_2h = snapshots_recentes[0][1]
        velocidade = round((odd_atual - odd_2h) / odd_2h * 100, 2) if odd_2h else 0

    casas_atuais = dados_atuais.get("casas", {})
    try:
        casas_abertura = json.loads(abertura[4])
    except Exception:
        casas_abertura = {}

    casas_mesma_direcao = 0
    total_casas = 0
    for casa, odd_atual_casa in casas_atuais.items():
        if casa in casas_abertura:
            total_casas += 1
            odd_ab = casas_abertura[casa]
            if magnitude < 0 and odd_atual_casa < odd_ab:
                casas_mesma_direcao += 1
            elif magnitude > 0 and odd_atual_casa > odd_ab:
                casas_mesma_direcao += 1

    consenso = round(casas_mesma_direcao / total_casas * 100, 1) if total_casas > 0 else 0

    pinnacle_lidera = False
    if dados_atuais.get("odd_pinnacle"):
        pinnacle_magnitude = round((dados_atuais["odd_pinnacle"] - (abertura[0] or 0)) / (abertura[0] or 1) * 100, 2)
        pinnacle_lidera = abs(pinnacle_magnitude) > abs(magnitude) * 0.8

    timestamp_abertura = abertura[5]
    try:
        dt_abertura = datetime.fromisoformat(timestamp_abertura)
        horas_desde_abertura = (datetime.now(timezone.utc) - dt_abertura).total_seconds() / 3600
    except Exception:
        horas_desde_abertura = 99

    steam_confirmado = (
        abs(magnitude) >= 3 and
        consenso >= 60 and
        horas_desde_abertura <= 4
    )

    return {
        "magnitude": magnitude,
        "velocidade": velocidade,
        "consenso": consenso,
        "pinnacle_lidera": pinnacle_lidera,
        "steam_confirmado": steam_confirmado,
        "horas_desde_abertura": round(horas_desde_abertura, 1),
        "odd_abertura": odd_abertura,
        "odd_atual": odd_atual
    }

def calcular_bonus_edge_score(steam_data):
    """
    Calcula pontos bônus no EDGE Score baseado no steam.
    Steam negativo: bloqueado pelo Gate 3
    Steam positivo fraco (3-5%): +3 pontos
    Steam positivo forte (>5%): +7 pontos
    Steam positivo + Pinnacle lidera: +12 pontos
    """
    if not steam_data or not steam_data["steam_confirmado"]:
        return 0

    magnitude = steam_data["magnitude"]

    if magnitude >= 0:
        return 0

    magnitude_abs = abs(magnitude)

    if steam_data["pinnacle_lidera"] and magnitude_abs >= 3:
        return 12
    elif magnitude_abs > 5:
        return 7
    elif magnitude_abs >= 3:
        return 3
    return 0

def salvar_steam_evento(sinal_id, jogo, mercado, steam_data, pontos_bonus):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    tipo = "positivo" if steam_data["magnitude"] < 0 else "negativo"

    c.execute('''
        INSERT INTO steam_eventos
        (sinal_id, jogo, mercado, odd_abertura, odd_atual, steam_magnitude,
         steam_velocidade, steam_consenso, pinnacle_lidera, tipo, timestamp, pontos_bonus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        sinal_id, jogo, mercado,
        steam_data["odd_abertura"], steam_data["odd_atual"],
        steam_data["magnitude"], steam_data["velocidade"],
        steam_data["consenso"], int(steam_data["pinnacle_lidera"]),
        tipo, datetime.now(timezone.utc).isoformat(), pontos_bonus
    ))
    conn.commit()
    conn.close()

def monitorar_jogos_ativos(jogos_com_sinais):
    """
    Monitora odds de todos os jogos com sinais ativos.
    Salva snapshots e detecta steam.
    """
    from atualizar_stats import carregar_medias

    resultados = {}

    for item in jogos_com_sinais:
        jogo = item["jogo"]
        mercado = item["mercado"]
        liga_key = item.get("liga_key", "soccer_epl")
        sinal_id = item.get("sinal_id")

        times = jogo.split(" vs ")
        if len(times) != 2:
            continue

        home, away = times
        dados = buscar_odds_todas_casas(liga_key, home, away, mercado)

        if not dados:
            continue

        abertura = buscar_snapshot_abertura(jogo, mercado)
        tipo = "snapshot" if abertura else "abertura"
        salvar_snapshot(jogo, mercado, dados, tipo)

        steam = calcular_steam(jogo, mercado, dados)
        if steam:
            bonus = calcular_bonus_edge_score(steam)
            resultados[jogo] = {
                "steam": steam,
                "bonus": bonus,
                "dados_odds": dados
            }

            if steam["steam_confirmado"] and bonus > 0:
                if sinal_id:
                    salvar_steam_evento(sinal_id, jogo, mercado, steam, bonus)
                print(f"Steam detectado: {jogo} | {mercado}")
                print(f"  Magnitude: {steam['magnitude']:+.1f}%")
                print(f"  Consenso: {steam['consenso']}% das casas")
                print(f"  Pinnacle lidera: {steam['pinnacle_lidera']}")
                print(f"  Bônus EDGE Score: +{bonus} pontos")

    return resultados

def gerar_alerta_steam(jogo, mercado, steam_data, sinal_id=None):
    """
    Gera mensagem de alerta para envio no Telegram.
    """
    tipo = "📈 STEAM POSITIVO" if steam_data["magnitude"] < 0 else "📉 Steam negativo"
    emoji = "🔥" if abs(steam_data["magnitude"]) > 5 else "⚡"

    msg = (
        f"{emoji} {tipo} DETECTADO\n\n"
        f"⚽ {jogo}\n"
        f"📌 Mercado: {mercado}\n\n"
        f"Odd abertura: {steam_data['odd_abertura']:.2f}\n"
        f"Odd atual:    {steam_data['odd_atual']:.2f}\n"
        f"Movimento:    {steam_data['magnitude']:+.1f}%\n"
        f"Velocidade:   {steam_data['velocidade']:+.1f}% (2h)\n"
        f"Consenso:     {steam_data['consenso']:.0f}% das casas\n"
        f"Pinnacle:     {'Lidera ✅' if steam_data['pinnacle_lidera'] else 'Segue'}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚡ Edge Protocol"
    )
    return msg

if __name__ == "__main__":
    criar_tabelas_steam()
    print("\nTeste de snapshot...")

    dados = buscar_odds_todas_casas("soccer_epl", "Arsenal", "Chelsea", "1x2_casa")
    if dados:
        print(f"Casas encontradas: {dados['total_casas']}")
        print(f"Odd média: {dados['odd_media']}")
        print(f"Odd Pinnacle: {dados['odd_pinnacle']}")
        salvar_snapshot("Arsenal vs Chelsea", "1x2_casa", dados, "abertura")
        print("Snapshot salvo.")
    else:
        print("Jogo não encontrado (normal se não houver jogos hoje).")