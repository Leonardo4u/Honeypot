import sqlite3
import os
import json
from datetime import datetime

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS job_execucoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_nome TEXT NOT NULL,
            janela_chave TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            reason_code TEXT,
            detalhes_json TEXT,
            UNIQUE(job_nome, janela_chave)
        )
    ''')
    conn.commit()
    conn.close()
    print("Banco de dados criado com sucesso.")


def garantir_tabela_execucoes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS job_execucoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_nome TEXT NOT NULL,
            janela_chave TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            reason_code TEXT,
            detalhes_json TEXT,
            UNIQUE(job_nome, janela_chave)
        )
    ''')
    conn.commit()
    conn.close()


def garantir_schema_minimo():
    if not os.path.exists(DB_PATH):
        criar_banco()
        return

    garantir_tabela_execucoes()


def validar_schema_minimo(tabelas_criticas=None):
    if tabelas_criticas is None:
        tabelas_criticas = ["sinais", "job_execucoes"]

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tabelas_existentes = {row[0] for row in c.fetchall()}
        faltantes = [nome for nome in tabelas_criticas if nome not in tabelas_existentes]
        return len(faltantes) == 0, faltantes
    except Exception as e:
        return False, [f"db_error:{str(e)}"]
    finally:
        if conn:
            conn.close()


def buscar_execucao_job(job_nome, janela_chave):
    garantir_tabela_execucoes()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        SELECT id, job_nome, janela_chave, status, started_at, finished_at, reason_code, detalhes_json
        FROM job_execucoes
        WHERE job_nome = ? AND janela_chave = ?
        LIMIT 1
        ''',
        (job_nome, janela_chave),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None

    detalhes = None
    if row[7]:
        try:
            detalhes = json.loads(row[7])
        except Exception:
            detalhes = row[7]

    return {
        "id": row[0],
        "job_nome": row[1],
        "janela_chave": row[2],
        "status": row[3],
        "started_at": row[4],
        "finished_at": row[5],
        "reason_code": row[6],
        "detalhes_json": detalhes,
    }


def iniciar_execucao_job(job_nome, janela_chave):
    garantir_tabela_execucoes()
    existente = buscar_execucao_job(job_nome, janela_chave)
    if existente:
        if existente["status"] in ("running", "ok", "degraded"):
            return {
                "iniciado": False,
                "reason_code": "idempotent_skip",
                "execucao": existente,
            }

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            '''
            UPDATE job_execucoes
            SET status = ?, started_at = ?, finished_at = NULL, reason_code = NULL, detalhes_json = NULL
            WHERE job_nome = ? AND janela_chave = ?
            ''',
            ("running", datetime.now().isoformat(), job_nome, janela_chave),
        )
        conn.commit()
        conn.close()
        return {
            "iniciado": True,
            "reason_code": "restarted_previous_failure",
            "execucao": buscar_execucao_job(job_nome, janela_chave),
        }

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        INSERT INTO job_execucoes (job_nome, janela_chave, status, started_at)
        VALUES (?, ?, ?, ?)
        ''',
        (job_nome, janela_chave, "running", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return {
        "iniciado": True,
        "reason_code": "started",
        "execucao": buscar_execucao_job(job_nome, janela_chave),
    }


def finalizar_execucao_job(job_nome, janela_chave, status, reason_code=None, detalhes_json=None):
    garantir_tabela_execucoes()
    detalhes_serializado = None
    if detalhes_json is not None:
        if isinstance(detalhes_json, str):
            detalhes_serializado = detalhes_json
        else:
            detalhes_serializado = json.dumps(detalhes_json, ensure_ascii=False)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        UPDATE job_execucoes
        SET status = ?, finished_at = ?, reason_code = ?, detalhes_json = ?
        WHERE job_nome = ? AND janela_chave = ?
        ''',
        (status, datetime.now().isoformat(), reason_code, detalhes_serializado, job_nome, janela_chave),
    )
    conn.commit()
    conn.close()
    return buscar_execucao_job(job_nome, janela_chave)

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

def sinal_existe(sinal_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM sinais WHERE id = ? LIMIT 1", (sinal_id,))
    existe = c.fetchone() is not None
    conn.close()
    return existe

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