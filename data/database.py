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
            fonte TEXT DEFAULT 'bot',
            message_id_vip INTEGER,
            message_id_free INTEGER,
            horario TEXT,
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
    garantir_schema_historico_sinais()
    conn.close()
    print("Banco de dados criado com sucesso.")


def garantir_colunas_sinais():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(sinais)")
    colunas_existentes = {row[1] for row in c.fetchall()}

    colunas_requeridas = {
        "message_id_vip": "INTEGER",
        "message_id_free": "INTEGER",
        "horario": "TEXT",
        "fonte": "TEXT DEFAULT 'bot'",
    }

    for coluna, tipo in colunas_requeridas.items():
        if coluna not in colunas_existentes:
            c.execute(f"ALTER TABLE sinais ADD COLUMN {coluna} {tipo}")

    conn.commit()
    conn.close()


def garantir_schema_historico_sinais(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sinais'")
    if not c.fetchone():
        conn.close()
        return

    c.execute("PRAGMA table_info(sinais)")
    colunas = {row[1] for row in c.fetchall()}
    if "fonte" not in colunas:
        c.execute("ALTER TABLE sinais ADD COLUMN fonte TEXT DEFAULT 'bot'")

    # Idempotencia: garante unicidade apenas para linhas historicas.
    c.execute(
        '''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sinais_historico_unico
        ON sinais(data, liga, jogo, mercado, odd)
        WHERE fonte = 'historico'
        '''
    )

    conn.commit()
    conn.close()


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
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()


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


def buscar_historico_time(time, ultimos=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        SELECT jogo, mercado, odd, resultado, lucro_unidades,
               ev_estimado, edge_score
        FROM sinais
        WHERE (jogo LIKE ? OR jogo LIKE ?)
        AND status = 'finalizado'
        ORDER BY criado_em DESC LIMIT ?
        ''',
        (f'{time} vs %', f'% vs {time}', ultimos),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def calcular_confianca_calibrada(time_casa, time_fora):
    hc = buscar_historico_time(time_casa)
    hf = buscar_historico_time(time_fora)
    nc, nf = len(hc), len(hf)
    conf = 50
    if nc >= 5 and nf >= 5:
        conf = 70
    if nc >= 10 and nf >= 10:
        conf = 75
    if nc >= 20 and nf >= 20:
        conf = 80

    if nc > 0 and nf > 0:
        wrc = sum(1 for r in hc if r[3] == 'verde') / nc
        wrf = sum(1 for r in hf if r[3] == 'verde') / nf
        wrm = (wrc + wrf) / 2
        if wrm >= 0.60 and nc >= 10:
            conf = min(100, conf + 15)
        elif wrm >= 0.55 and nc >= 10:
            conf = min(100, conf + 8)
        elif wrm < 0.45 and nc >= 10:
            conf = max(50, conf - 15)

    return conf


def resumo_calibracao(n_minimo=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''SELECT COUNT(*),
           SUM(CASE WHEN resultado='verde' THEN 1 ELSE 0 END),
           AVG(ev_estimado), AVG(edge_score)
           FROM sinais WHERE status='finalizado' '''
    )
    row = c.fetchone()
    conn.close()

    total = row[0] or 0
    if total < n_minimo:
        return {"total": total, "faltam": n_minimo - total, "calibrado": False}

    v = row[1] or 0
    wr = v / total
    return {
        "total": total,
        "faltam": 0,
        "win_rate_real": round(wr * 100, 1),
        "ev_medio_pct": round((row[2] or 0) * 100, 2),
        "score_medio": round(row[3] or 0, 1),
        "calibrado": wr >= 0.55,
        "alerta": wr < 0.50,
    }

if __name__ == "__main__":
    criar_banco()