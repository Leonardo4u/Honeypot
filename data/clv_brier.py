import sqlite3
import requests
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from database import sinal_existe

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT_DIR, "data"))
PICKS_LOG_PATH = os.path.join(BOT_DATA_DIR, "picks_log.csv")
API_KEY = os.getenv("ODDS_API_KEY")


def _sinal_existe_em_path(sinal_id, db_path=None):
    """Valida existência de sinal no banco alvo, respeitando db_path opcional."""
    if db_path is None:
        return sinal_existe(sinal_id)
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM sinais WHERE id = ? LIMIT 1", (sinal_id,))
        return c.fetchone() is not None
    finally:
        conn.close()

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
    if not sinal_existe(sinal_id):
        print(f"[clv_link_invalid] sinal_id inexistente: {sinal_id}")
        return False

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id FROM clv_tracking WHERE sinal_id = ?", (sinal_id,))
    clv_exists = c.fetchone() is not None
    c.execute("SELECT id FROM brier_tracking WHERE sinal_id = ?", (sinal_id,))
    brier_exists = c.fetchone() is not None

    if not clv_exists:
        c.execute('''
            INSERT INTO clv_tracking (sinal_id, jogo, mercado, odd_entrada, timestamp_entrada)
            VALUES (?, ?, ?, ?, ?)
        ''', (sinal_id, jogo, mercado, odd_entrada, datetime.now(timezone.utc).isoformat()))

    if not brier_exists:
        c.execute('''
            INSERT INTO brier_tracking (sinal_id, jogo, mercado, prob_prevista)
            VALUES (?, ?, ?, ?)
        ''', (sinal_id, jogo, mercado, prob_prevista))

    conn.commit()
    conn.close()
    return True

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

def atualizar_clv(sinal_id, odd_fechamento, outcome=None, db_path=None):
    path = db_path or DB_PATH
    if not _sinal_existe_em_path(sinal_id, db_path=path):
        print(f"[clv_link_invalid] sinal_id inexistente no fechamento: {sinal_id}")
        return None

    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("PRAGMA table_info(sinais)")
    colunas_sinais = {str(r[1]) for r in c.fetchall()}
    prediction_select = "prediction_id" if "prediction_id" in colunas_sinais else "NULL"
    c.execute(
        f"SELECT liga, jogo, horario, {prediction_select} FROM sinais WHERE id = ?",
        (sinal_id,),
    )
    sinal_row = c.fetchone()

    c.execute("SELECT odd_entrada, status, odd_fechamento, clv_percentual FROM clv_tracking WHERE sinal_id = ?", (sinal_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    odd_entrada, status, odd_fechamento_atual, clv_existente = row
    if status == "fechado" and odd_fechamento_atual is not None:
        conn.close()
        return clv_existente

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

    # INTEGRATION: persistir closing_odds no picks_log para CLV por pick no dashboard.
    try:
        if sinal_row:
            liga, jogo, horario, prediction_id = sinal_row
            from model.picks_log import PickLogger

            pick_logger = PickLogger(PICKS_LOG_PATH)
            pred_id = pick_logger.find_prediction_id(
                league=liga or "",
                jogo=jogo or "",
                timestamp_ref=horario,
                prediction_id=prediction_id,
            )
            if pred_id and outcome in (0, 1):
                pick_logger.update_outcome(pred_id, outcome=int(outcome), closing_odds=odd_fechamento)
    except Exception as e:
        print(f"[WARN] atualizar_clv -> picks_log sync falhou para sinal_id={sinal_id}: {e}")

    return clv

def atualizar_brier(sinal_id, acertou):
    if not sinal_existe(sinal_id):
        print(f"[brier_link_invalid] sinal_id inexistente na atualização: {sinal_id}")
        return None

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT prob_prevista, resultado_real, brier_score FROM brier_tracking WHERE sinal_id = ?", (sinal_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    prob, resultado_existente, brier_existente = row
    if resultado_existente is not None:
        conn.close()
        return brier_existente

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