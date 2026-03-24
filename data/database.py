import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")

def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sinais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            liga TEXT,
            jogo TEXT,
            mercado TEXT,
            odd REAL,
            ev_estimado REAL,
            edge_score INTEGER,
            stake_unidades REAL,
            status TEXT DEFAULT 'pendente',
            resultado TEXT,
            lucro_unidades REAL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS banca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            valor_inicial REAL,
            valor_atual REAL,
            roi_percentual REAL,
            total_sinais INTEGER DEFAULT 0,
            vitorias INTEGER DEFAULT 0,
            derrotas INTEGER DEFAULT 0,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("Banco de dados criado com sucesso.")

def inserir_sinal(liga, jogo, mercado, odd, ev, score, stake, message_id_vip=None, message_id_free=None, horario=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    from datetime import date
    c.execute('''
        INSERT INTO sinais (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades, message_id_vip, message_id_free, horario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (str(date.today()), liga, jogo, mercado, odd, ev, score, stake, message_id_vip, message_id_free, horario))
    conn.commit()
    sinal_id = c.lastrowid
    conn.close()
    return sinal_id

def atualizar_resultado(sinal_id, resultado, lucro):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE sinais SET status = 'finalizado', resultado = ?, lucro_unidades = ?
        WHERE id = ?
    ''', (resultado, lucro, sinal_id))
    conn.commit()
    conn.close()

def buscar_sinais_hoje():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    from datetime import date
    c.execute("SELECT * FROM sinais WHERE data = ?", (str(date.today()),))
    rows = c.fetchall()
    conn.close()
    return rows

def resumo_mensal():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN resultado = 'verde' THEN 1 ELSE 0 END) as vitorias,
            SUM(CASE WHEN resultado = 'vermelho' THEN 1 ELSE 0 END) as derrotas,
            SUM(lucro_unidades) as lucro_total
        FROM sinais
        WHERE status = 'finalizado'
    ''')
    row = c.fetchone()
    conn.close()
    return row

if __name__ == "__main__":
    criar_banco()