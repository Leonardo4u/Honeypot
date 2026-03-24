import sqlite3
import requests
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
API_KEY = os.getenv("ODDS_API_KEY")

def criar_tabelas_validacao():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS clv_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinal_id INTEGER,
            jogo TEXT,
            mercado TEXT,
            odd_entrada REAL,
            odd_fechamento REAL,
            clv_percentual REAL,
            timestamp_entrada TEXT,
            timestamp_fechamento TEXT,
            status TEXT DEFAULT 'aguardando',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS brier_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sinal_id INTEGER,
            jogo TEXT,
            mercado TEXT,
            prob_prevista REAL,
            resultado_real INTEGER,
            brier_score REAL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("Tabelas de validação criadas.")

def registrar_aposta_clv(sinal_id, jogo, mercado, odd_entrada, prob_prevista):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        INSERT INTO clv_tracking (sinal_id, jogo, mercado, odd_entrada, timestamp_entrada)
        VALUES (?, ?, ?, ?, ?)
    ''', (sinal_id, jogo, mercado, odd_entrada, datetime.now(timezone.utc).isoformat()))

    c.execute('''
        INSERT INTO brier_tracking (sinal_id, jogo, mercado, prob_prevista)
        VALUES (?, ?, ?, ?)
    ''', (sinal_id, jogo, mercado, prob_prevista))

    conn.commit()
    conn.close()

def buscar_odd_fechamento_pinnacle(jogo, mercado, liga_key):
    if not API_KEY:
        return None

    home, away = jogo.split(" vs ")
    url = f"https://api.the-odds-api.com/v4/sports/{liga_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        jogos = response.json()
        for j in jogos:
            h = j.get("home_team", "").lower()
            a = j.get("away_team", "").lower()
            if home.lower() in h and away.lower() in a:
                for bm in j.get("bookmakers", []):
                    if bm["key"] == "pinnacle":
                        for market in bm.get("markets", []):
                            if mercado == "1x2_casa" and market["key"] == "h2h":
                                for o in market["outcomes"]:
                                    if o["name"] == j["home_team"]:
                                        return o["price"]
                            elif mercado == "over_2.5" and market["key"] == "totals":
                                for o in market["outcomes"]:
                                    if o["name"] == "Over":
                                        return o["price"]
        return None

    except Exception as e:
        print(f"Erro ao buscar odd Pinnacle: {e}")
        return None

def atualizar_clv(sinal_id, odd_fechamento):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT odd_entrada FROM clv_tracking WHERE sinal_id = ?", (sinal_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    odd_entrada = row[0]
    clv = (odd_fechamento / odd_entrada - 1) * 100
    clv = round(clv, 3)

    c.execute('''
        UPDATE clv_tracking
        SET odd_fechamento = ?, clv_percentual = ?,
            timestamp_fechamento = ?, status = 'fechado'
        WHERE sinal_id = ?
    ''', (odd_fechamento, clv, datetime.now(timezone.utc).isoformat(), sinal_id))

    conn.commit()
    conn.close()
    return clv

def atualizar_brier(sinal_id, acertou):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prob_prevista FROM brier_tracking WHERE sinal_id = ?", (sinal_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    prob = row[0]
    resultado = 1 if acertou else 0
    brier = round((prob - resultado) ** 2, 4)

    c.execute('''
        UPDATE brier_tracking
        SET resultado_real = ?, brier_score = ?
        WHERE sinal_id = ?
    ''', (resultado, brier, sinal_id))

    conn.commit()
    conn.close()
    return brier

def calcular_metricas():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        SELECT clv_percentual FROM clv_tracking
        WHERE status = 'fechado' AND clv_percentual IS NOT NULL
    ''')
    clvs = [r[0] for r in c.fetchall()]

    c.execute('''
        SELECT brier_score FROM brier_tracking
        WHERE brier_score IS NOT NULL
    ''')
    briers = [r[0] for r in c.fetchall()]

    c.execute('''
        SELECT prob_prevista, resultado_real FROM brier_tracking
        WHERE resultado_real IS NOT NULL
    ''')
    calibracao = c.fetchall()

    conn.close()

    clv_medio = round(sum(clvs) / len(clvs), 2) if clvs else 0
    clv_positivo_pct = round(sum(1 for c in clvs if c > 0) / len(clvs) * 100, 1) if clvs else 0
    brier_medio = round(sum(briers) / len(briers), 4) if briers else 0

    return {
        "clv_medio": clv_medio,
        "clv_positivo_pct": clv_positivo_pct,
        "total_apostas_clv": len(clvs),
        "brier_medio": brier_medio,
        "total_apostas_brier": len(briers),
        "calibracao": calibracao,
        "clvs": clvs
    }

def buscar_sinais_para_fechar():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT ct.sinal_id, ct.jogo, ct.mercado, s.liga
        FROM clv_tracking ct
        JOIN sinais s ON s.id = ct.sinal_id
        WHERE ct.status = 'aguardando'
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    criar_tabelas_validacao()
    print("Sistema de validação iniciado.")

    metricas = calcular_metricas()
    print(f"\nCLV Médio: {metricas['clv_medio']}%")
    print(f"% CLV Positivo: {metricas['clv_positivo_pct']}%")
    print(f"Brier Score Médio: {metricas['brier_medio']}")

    if metricas['brier_medio'] > 0:
        if metricas['brier_medio'] < 0.20:
            print("Calibração: EXCELENTE")
        elif metricas['brier_medio'] < 0.25:
            print("Calibração: BOA")
        else:
            print("Calibração: SUPERESTIMANDO — revisar modelo")