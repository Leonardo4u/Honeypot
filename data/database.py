import sqlite3
import os
import json
import logging
from contextlib import contextmanager
from datetime import datetime, UTC

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
logger = logging.getLogger(__name__)
_WAL_CONFIGURED_PATHS = set()

COLUNAS_SINAIS_ALLOWLIST = {
    "message_id_vip": "INTEGER",
    "message_id_free": "INTEGER",
    "horario": "TEXT",
    "fonte": "TEXT DEFAULT 'bot'",
    "fixture_id_api": "TEXT",
    "fixture_data_api": "TEXT",
    "app_version": "TEXT DEFAULT 'dev'",
}


def _validar_coluna_sinais(coluna, tipo):
    tipo_esperado = COLUNAS_SINAIS_ALLOWLIST.get(coluna)
    return tipo_esperado is not None and tipo_esperado == tipo


def _adicionar_coluna_segura(cursor, tabela, coluna, tipo):
    if tabela != "sinais" or not _validar_coluna_sinais(coluna, tipo):
        raise ValueError(f"DDL nao permitido para coluna '{coluna}'")
    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


@contextmanager
def get_conn(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        if path not in _WAL_CONFIGURED_PATHS:
            conn.execute("PRAGMA journal_mode=WAL")
            _WAL_CONFIGURED_PATHS.add(path)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def criar_banco():
    with get_conn() as conn:
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
            fixture_id_api TEXT,
            fixture_data_api TEXT,
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
        c.execute('''
        CREATE TABLE IF NOT EXISTS operation_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            actor TEXT NOT NULL,
            acao TEXT NOT NULL,
            efeito TEXT NOT NULL,
            detalhes_json TEXT
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS operation_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            severidade TEXT NOT NULL,
            codigo TEXT NOT NULL,
            playbook_id TEXT,
            detalhes_json TEXT
        )
    ''')
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()
    garantir_tabelas_operacionais()
    print("Banco de dados criado com sucesso.")


def garantir_colunas_sinais():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sinais)")
        colunas_existentes = {row[1] for row in c.fetchall()}

        colunas_requeridas = COLUNAS_SINAIS_ALLOWLIST

        for coluna, tipo in colunas_requeridas.items():
            if coluna not in colunas_existentes:
                _adicionar_coluna_segura(c, "sinais", coluna, tipo)


def garantir_schema_historico_sinais(db_path=None):
    path = db_path or DB_PATH
    with get_conn(path) as conn:
        c = conn.cursor()

        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sinais'")
        if not c.fetchone():
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


def garantir_tabela_execucoes():
    with get_conn() as conn:
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



def garantir_tabelas_operacionais():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS operation_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            actor TEXT NOT NULL,
            acao TEXT NOT NULL,
            efeito TEXT NOT NULL,
            detalhes_json TEXT
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS operation_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            severidade TEXT NOT NULL,
            codigo TEXT NOT NULL,
            playbook_id TEXT,
            detalhes_json TEXT
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS model_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            match_id TEXT,
            market TEXT,
            lambda_home REAL,
            lambda_away REAL,
            sharp_score REAL,
            edge REAL,
            shrinkage_home REAL,
            shrinkage_away REAL,
            detalhes_json TEXT
        )
        '''
    )



def garantir_schema_minimo():
    if not os.path.exists(DB_PATH):
        criar_banco()
        return

    garantir_tabela_execucoes()
    garantir_tabelas_operacionais()
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()


def validar_schema_minimo(tabelas_criticas=None):
    if tabelas_criticas is None:
        tabelas_criticas = ["sinais", "job_execucoes"]

    try:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            tabelas_existentes = {row[0] for row in c.fetchall()}
            faltantes = [nome for nome in tabelas_criticas if nome not in tabelas_existentes]
            return len(faltantes) == 0, faltantes
    except sqlite3.DatabaseError as e:
        logger.exception("falha_validar_schema_minimo")
        return False, [f"db_error:{str(e)}"]
    except Exception as e:
        logger.exception("falha_inesperada_validar_schema_minimo")
        return False, [f"db_error:{str(e)}"]


def _select_execucao_job(cursor, job_nome, janela_chave):
    cursor.execute(
        '''
        SELECT id, job_nome, janela_chave, status, started_at, finished_at, reason_code, detalhes_json
        FROM job_execucoes
        WHERE job_nome = ? AND janela_chave = ?
        LIMIT 1
        ''',
        (job_nome, janela_chave),
    )
    return _row_para_execucao(cursor.fetchone())


def buscar_execucao_job(job_nome, janela_chave):
    garantir_tabela_execucoes()
    with get_conn() as conn:
        c = conn.cursor()
        return _select_execucao_job(c, job_nome, janela_chave)


def _row_para_execucao(row):
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
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        started_at = datetime.now(UTC).isoformat()

        c.execute(
            '''
            INSERT OR IGNORE INTO job_execucoes (job_nome, janela_chave, status, started_at)
            VALUES (?, ?, ?, ?)
            ''',
            (job_nome, janela_chave, "running", started_at),
        )

        if c.rowcount == 1:
            return {
                "iniciado": True,
                "reason_code": "started",
                "execucao": _select_execucao_job(c, job_nome, janela_chave),
            }

        existente = _select_execucao_job(c, job_nome, janela_chave)
        if existente and existente["status"] in ("running", "ok", "degraded"):
            return {
                "iniciado": False,
                "reason_code": "idempotent_skip",
                "execucao": existente,
            }

        c.execute(
            '''
            UPDATE job_execucoes
            SET status = ?, started_at = ?, finished_at = NULL, reason_code = NULL, detalhes_json = NULL
            WHERE job_nome = ? AND janela_chave = ?
            ''',
            ("running", started_at, job_nome, janela_chave),
        )
        return {
            "iniciado": True,
            "reason_code": "restarted_previous_failure",
            "execucao": _select_execucao_job(c, job_nome, janela_chave),
        }


def finalizar_execucao_job(job_nome, janela_chave, status, reason_code=None, detalhes_json=None):
    garantir_tabela_execucoes()
    detalhes_serializado = None
    if detalhes_json is not None:
        if isinstance(detalhes_json, str):
            detalhes_serializado = detalhes_json
        else:
            detalhes_serializado = json.dumps(detalhes_json, ensure_ascii=False)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            UPDATE job_execucoes
            SET status = ?, finished_at = ?, reason_code = ?, detalhes_json = ?
            WHERE job_nome = ? AND janela_chave = ?
            ''',
            (status, datetime.now(UTC).isoformat(), reason_code, detalhes_serializado, job_nome, janela_chave),
        )
    return buscar_execucao_job(job_nome, janela_chave)

def inserir_sinal(liga, jogo, mercado, odd, ev, score, stake, message_id_vip=None, message_id_free=None, horario=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO sinais (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades, message_id_vip, message_id_free, horario, app_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ((datetime.now(UTC).date().isoformat()), liga, jogo, mercado, odd, ev, score, stake, message_id_vip, message_id_free, horario, os.getenv("EDGE_VERSION", "dev")))
        return c.lastrowid

def atualizar_resultado(sinal_id, resultado, lucro):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE sinais SET status = 'finalizado', resultado = ?, lucro_unidades = ?
            WHERE id = ?
        ''', (resultado, lucro, sinal_id))


def atualizar_fixture_referencia(sinal_id, fixture_id_api=None, fixture_data_api=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            UPDATE sinais
            SET fixture_id_api = COALESCE(?, fixture_id_api),
                fixture_data_api = COALESCE(?, fixture_data_api)
            WHERE id = ?
            ''',
            (fixture_id_api, fixture_data_api, sinal_id),
        )

def sinal_existe(sinal_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM sinais WHERE id = ? LIMIT 1", (sinal_id,))
        return c.fetchone() is not None

def buscar_sinais_hoje():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM sinais WHERE data = ?", (datetime.now(UTC).date().isoformat(),))
        return c.fetchall()


def calcular_perda_diaria_unidades(data_ref=None):
    data_alvo = data_ref or datetime.now(UTC).strftime("%Y-%m-%d")
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT SUM(CASE WHEN lucro_unidades < 0 THEN lucro_unidades ELSE 0 END)
            FROM sinais
            WHERE data = ?
              AND status = 'finalizado'
            ''',
            (data_alvo,),
        )
        row = c.fetchone()
        return float(row[0] or 0.0)


def calcular_exposicao_pendente_unidades(janela_horas=6):
    agora = datetime.now(UTC)
    limite = agora.timestamp() + max(1, int(janela_horas)) * 3600
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT horario, stake_unidades
            FROM sinais
            WHERE status = 'pendente'
              AND horario IS NOT NULL
              AND stake_unidades IS NOT NULL
            '''
        )
        rows = c.fetchall()

    total = 0.0
    for horario, stake in rows:
        try:
            ts = datetime.strptime(horario, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
            if agora.timestamp() <= ts <= limite:
                total += float(stake or 0.0)
        except Exception:
            continue
    return round(total, 4)


def registrar_auditoria_acao(actor, acao, efeito, detalhes=None):
    garantir_tabelas_operacionais()
    detalhes_json = None
    if detalhes is not None:
        detalhes_json = json.dumps(detalhes, ensure_ascii=False)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO operation_audit (ocorrido_em, actor, acao, efeito, detalhes_json)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (datetime.now(UTC).isoformat(), actor, acao, efeito, detalhes_json),
        )


def registrar_alerta_operacional(severidade, codigo, playbook_id=None, detalhes=None):
    garantir_tabelas_operacionais()
    detalhes_json = None
    if detalhes is not None:
        detalhes_json = json.dumps(detalhes, ensure_ascii=False)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO operation_alerts (ocorrido_em, severidade, codigo, playbook_id, detalhes_json)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (datetime.now(UTC).isoformat(), severidade, codigo, playbook_id, detalhes_json),
        )


def obter_slo_disponibilidade_ciclo(dias=7):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status IN ('ok', 'degraded') THEN 1 ELSE 0 END) AS saudaveis
            FROM job_execucoes
            WHERE started_at >= datetime('now', ?)
            ''',
            (f'-{int(max(1, dias))} day',),
        )
        row = c.fetchone() or (0, 0)
        total = int(row[0] or 0)
        saudaveis = int(row[1] or 0)
    disponibilidade = (saudaveis / total) if total > 0 else 1.0
    return {
        "total": total,
        "saudaveis": saudaveis,
        "disponibilidade": round(disponibilidade, 4),
    }


def registrar_diagnostico_modelo(
    match_id,
    market,
    lambda_home,
    lambda_away,
    sharp_score,
    edge,
    shrinkage_home,
    shrinkage_away,
    detalhes=None,
):
    garantir_tabelas_operacionais()
    detalhes_json = json.dumps(detalhes or {}, ensure_ascii=False)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO model_diagnostics (
                ocorrido_em,
                match_id,
                market,
                lambda_home,
                lambda_away,
                sharp_score,
                edge,
                shrinkage_home,
                shrinkage_away,
                detalhes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                datetime.now(UTC).isoformat(),
                match_id,
                market,
                lambda_home,
                lambda_away,
                sharp_score,
                edge,
                shrinkage_home,
                shrinkage_away,
                detalhes_json,
            ),
        )

def resumo_mensal():
    with get_conn() as conn:
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
        return c.fetchone()


def buscar_historico_time(time, ultimos=20):
    with get_conn() as conn:
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
        return c.fetchall()


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


def buscar_metricas_qualidade_liga_mercado(liga, mercado, fonte_preferencial="historico"):
    """
    Retorna agregados historicos para prior de qualidade por liga+mercado.
    Prioriza fonte historica quando disponivel; caso contrario, usa qualquer fonte.
    """
    with get_conn() as conn:
        c = conn.cursor()

        def _query(fonte=None):
            if fonte:
                c.execute(
                    '''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN resultado = 'verde' THEN 1 ELSE 0 END) as vitorias,
                        SUM(COALESCE(lucro_unidades, 0)) as lucro_total
                    FROM sinais
                    WHERE status = 'finalizado'
                      AND liga = ?
                      AND mercado = ?
                      AND fonte = ?
                    ''',
                    (liga, mercado, fonte),
                )
            else:
                c.execute(
                    '''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN resultado = 'verde' THEN 1 ELSE 0 END) as vitorias,
                        SUM(COALESCE(lucro_unidades, 0)) as lucro_total
                    FROM sinais
                    WHERE status = 'finalizado'
                      AND liga = ?
                      AND mercado = ?
                    ''',
                    (liga, mercado),
                )
            row = c.fetchone() or (0, 0, 0)
            total = int(row[0] or 0)
            vitorias = int(row[1] or 0)
            lucro_total = float(row[2] or 0.0)
            return total, vitorias, lucro_total

        total, vitorias, lucro_total = _query(fonte_preferencial)
        fonte_usada = fonte_preferencial if total > 0 else "todas"

        if total == 0:
            total, vitorias, lucro_total = _query()

    win_rate = (vitorias / total) if total > 0 else 0.0
    roi_pct = ((lucro_total / total) * 100.0) if total > 0 else 0.0

    return {
        "liga": liga,
        "mercado": mercado,
        "total": total,
        "vitorias": vitorias,
        "win_rate": round(win_rate, 4),
        "roi_pct": round(roi_pct, 4),
        "lucro_total": round(lucro_total, 4),
        "fonte": fonte_usada,
    }


def resumo_calibracao(n_minimo=50):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''SELECT COUNT(*),
               SUM(CASE WHEN resultado='verde' THEN 1 ELSE 0 END),
               AVG(ev_estimado), AVG(edge_score)
               FROM sinais WHERE status='finalizado' '''
        )
        row = c.fetchone()

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