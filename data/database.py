import sqlite3
import os
import json
import logging
from contextlib import contextmanager
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

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
    "canary_tag": "TEXT DEFAULT NULL",
}


def _validar_coluna_sinais(coluna, tipo):
    tipo_esperado = COLUNAS_SINAIS_ALLOWLIST.get(coluna)
    return tipo_esperado is not None and tipo_esperado == tipo


def _adicionar_coluna_segura(cursor, tabela, coluna, tipo):
    if tabela != "sinais" or not _validar_coluna_sinais(coluna, tipo):
        raise ValueError(f"DDL nao permitido para coluna '{coluna}'")
    cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


@contextmanager
def get_conn(db_path: Optional[str] = None):
    """Context manager original  mantido para compatibilidade total."""
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


# FIX-08: context manager simples para hot paths que no precisam
# de row_factory nem de WAL tracking  reduz overhead de connect/close
@contextmanager
def get_db_connection(db_path: Optional[str] = None):
    """
    Context manager leve para hot paths de leitura/escrita simples.
    No configura row_factory nem WAL (use get_conn para operaes
    que precisam de Row objects ou em primeira conexo ao banco).
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def criar_banco():
    schema_ja_existia = False
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sinais'")
        schema_ja_existia = c.fetchone() is not None
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
            canary_tag TEXT DEFAULT NULL,
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
        c.execute('''
        CREATE TABLE IF NOT EXISTS fallback_cycle_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            job_nome TEXT,
            janela_chave TEXT,
            liga TEXT,
            jogo TEXT,
            mercado TEXT,
            motivo_fallback TEXT,
            detalhes_json TEXT
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS shadow_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            data_ref TEXT NOT NULL,
            liga TEXT NOT NULL,
            jogo TEXT NOT NULL,
            mercado TEXT NOT NULL,
            prediction_id_baseline TEXT,
            prediction_id_advanced TEXT,
            prob_baseline REAL,
            prob_advanced REAL,
            outcome INTEGER,
            brier_baseline REAL,
            brier_advanced REAL,
            closing_odds REAL,
            clv_baseline REAL,
            clv_advanced REAL,
            shadow_mode INTEGER DEFAULT 1,
            detalhes_json TEXT
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS blend_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liga TEXT,
            mercado TEXT,
            w_poisson REAL NOT NULL,
            w_mercado REAL NOT NULL,
            min_amostra INTEGER DEFAULT 50,
            versao TEXT DEFAULT 'v1',
            gerado_em TEXT NOT NULL,
            UNIQUE(liga, mercado)
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS walk_forward_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fold_id TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            brier_val REAL,
            brier_test REAL,
            roi_test REAL,
            n_picks INTEGER,
            criado_em TEXT NOT NULL,
            UNIQUE(fold_id)
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS segment_thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liga TEXT,
            mercado TEXT,
            ev_floor REAL,
            confidence_floor REAL,
            edge_cutoff REAL,
            min_amostra INTEGER DEFAULT 50,
            versao TEXT DEFAULT 'v1',
            gerado_em TEXT NOT NULL,
            UNIQUE(liga, mercado)
        )
    ''')
        c.execute('''
        CREATE TABLE IF NOT EXISTS reliability_deciles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referencia_semana TEXT NOT NULL,
            mercado TEXT NOT NULL,
            decil INTEGER NOT NULL,
            p_prevista REAL,
            p_observada REAL,
            n INTEGER NOT NULL,
            ece_contribution REAL,
            ece REAL,
            mce REAL,
            criado_em TEXT NOT NULL,
            UNIQUE(referencia_semana, mercado, decil)
        )
    ''')
        garantir_indices_desempenho(c)
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()
    garantir_tabelas_operacionais()
    if not schema_ja_existia:
        print("Banco de dados criado com sucesso.")


def garantir_indices_desempenho(cursor=None):
    statements = [
        '''
        CREATE INDEX IF NOT EXISTS idx_sinais_data_status
        ON sinais(data, status)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_sinais_status_horario
        ON sinais(status, horario)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_sinais_duplicate_lookup
        ON sinais(
            date(COALESCE(criado_em, data)),
            lower(trim(liga)),
            lower(trim(jogo)),
            lower(trim(mercado))
        )
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_fallback_cycle_job_window
        ON fallback_cycle_details(job_nome, janela_chave, ocorrido_em)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_shadow_pred_lookup
        ON shadow_predictions(data_ref, liga, jogo, mercado)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_shadow_pred_settlement
        ON shadow_predictions(outcome, ocorrido_em)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_walk_forward_period
        ON walk_forward_results(data_inicio, data_fim)
        ''',
        '''
        CREATE INDEX IF NOT EXISTS idx_reliability_market_week
        ON reliability_deciles(referencia_semana, mercado)
        ''',
    ]

    if cursor is not None:
        for stmt in statements:
            cursor.execute(stmt)
        return

    with get_conn() as conn:
        c = conn.cursor()
        for stmt in statements:
            c.execute(stmt)


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
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS fallback_cycle_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            job_nome TEXT,
            janela_chave TEXT,
            liga TEXT,
            jogo TEXT,
            mercado TEXT,
            motivo_fallback TEXT,
            detalhes_json TEXT
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS shadow_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ocorrido_em TEXT NOT NULL,
            data_ref TEXT NOT NULL,
            liga TEXT NOT NULL,
            jogo TEXT NOT NULL,
            mercado TEXT NOT NULL,
            prediction_id_baseline TEXT,
            prediction_id_advanced TEXT,
            prob_baseline REAL,
            prob_advanced REAL,
            outcome INTEGER,
            brier_baseline REAL,
            brier_advanced REAL,
            closing_odds REAL,
            clv_baseline REAL,
            clv_advanced REAL,
            shadow_mode INTEGER DEFAULT 1,
            detalhes_json TEXT
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS blend_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liga TEXT,
            mercado TEXT,
            w_poisson REAL NOT NULL,
            w_mercado REAL NOT NULL,
            min_amostra INTEGER DEFAULT 50,
            versao TEXT DEFAULT 'v1',
            gerado_em TEXT NOT NULL,
            UNIQUE(liga, mercado)
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS walk_forward_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fold_id TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT NOT NULL,
            brier_val REAL,
            brier_test REAL,
            roi_test REAL,
            n_picks INTEGER,
            criado_em TEXT NOT NULL,
            UNIQUE(fold_id)
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS segment_thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liga TEXT,
            mercado TEXT,
            ev_floor REAL,
            confidence_floor REAL,
            edge_cutoff REAL,
            min_amostra INTEGER DEFAULT 50,
            versao TEXT DEFAULT 'v1',
            gerado_em TEXT NOT NULL,
            UNIQUE(liga, mercado)
        )
        '''
    )
        c.execute(
        '''
        CREATE TABLE IF NOT EXISTS reliability_deciles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referencia_semana TEXT NOT NULL,
            mercado TEXT NOT NULL,
            decil INTEGER NOT NULL,
            p_prevista REAL,
            p_observada REAL,
            n INTEGER NOT NULL,
            ece_contribution REAL,
            ece REAL,
            mce REAL,
            criado_em TEXT NOT NULL,
            UNIQUE(referencia_semana, mercado, decil)
        )
        '''
    )
        garantir_indices_desempenho(c)


def garantir_schema_minimo():
    """
    Ponto de entrada para garantia incremental de schema.
    Chama bootstrap_completo() para cobrir todos os casos.
    """
    if not os.path.exists(DB_PATH):
        criar_banco()
        return

    garantir_tabela_execucoes()
    garantir_tabelas_operacionais()
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()
    garantir_indices_desempenho()


# FIX-11: ponto nico e determinstico de bootstrap de schema
def bootstrap_completo(db_path=None):
    """
    Inicializa ou migra o schema completo do banco em ordem determinstica.

     o nico ponto de entrada recomendado para fresh setup.
    Idempotente  seguro de chamar mltiplas vezes.

    Ordem de execuo:
      1. criar_banco()               tabelas base e schema principal
      2. garantir_colunas_sinais()   colunas opcionais da tabela sinais
      3. garantir_schema_historico_sinais()  ndice de deduplicao histrica
      4. garantir_tabela_execucoes()         tabela de idempotncia de jobs
      5. garantir_tabelas_operacionais()     auditoria, alertas, diagnsticos
    """
    # Se um db_path customizado foi passado, redirecionar temporariamente
    # (usado em testes com banco temporrio)
    if db_path is not None:
        original_db_path = globals().get("DB_PATH")
        # No alteramos o mdulo global  chamamos diretamente cada garantia
        _bootstrap_em_path(db_path)
        return

    criar_banco()
    garantir_colunas_sinais()
    garantir_schema_historico_sinais()
    garantir_tabela_execucoes()
    garantir_tabelas_operacionais()


def _bootstrap_em_path(db_path):
    """Executa bootstrap em um caminho de banco especfico (para testes)."""
    original_db_path = DB_PATH
    try:
        globals()["DB_PATH"] = db_path
        criar_banco()
        garantir_colunas_sinais()
        garantir_schema_historico_sinais(db_path=db_path)
        garantir_tabela_execucoes()
        garantir_tabelas_operacionais()
    finally:
        globals()["DB_PATH"] = original_db_path


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

def inserir_sinal(
    liga: str,
    jogo: str,
    mercado: str,
    odd: float,
    ev: float,
    score: float,
    stake: float,
    message_id_vip: Optional[int] = None,
    message_id_free: Optional[int] = None,
    horario: Optional[str] = None,
    canary_tag: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO sinais (data, liga, jogo, mercado, odd, ev_estimado, edge_score, stake_unidades, message_id_vip, message_id_free, horario, app_version, canary_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ((datetime.now(UTC).date().isoformat()), liga, jogo, mercado, odd, ev, score, stake, message_id_vip, message_id_free, horario, os.getenv("EDGE_VERSION", "dev"), canary_tag))
        if c.lastrowid is None:
            raise RuntimeError("Falha ao inserir sinal: lastrowid ausente")
        return int(c.lastrowid)


def contar_sinais_duplicados_mesmo_dia(liga, team_home, team_away, mercado, data_ref=None):
    """Conta sinais com mesmo jogo/mercado registrados no mesmo dia de criao."""
    data_alvo = data_ref or datetime.now(UTC).date().isoformat()
    jogo = f"{str(team_home).strip()} vs {str(team_away).strip()}"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT COUNT(*)
            FROM sinais
            WHERE lower(trim(liga)) = lower(trim(?))
              AND lower(trim(jogo)) = lower(trim(?))
              AND lower(trim(mercado)) = lower(trim(?))
              AND date(COALESCE(criado_em, data)) = date(?)
            ''',
            (liga, jogo, mercado, data_alvo),
        )
        row = c.fetchone()
        return int(row[0] or 0)


def listar_sinais_duplicados_mesmo_dia(data_ref=None):
    """Lista agrupamentos duplicados por dia para auditoria operacional."""
    params = []
    where_data = ""
    if data_ref:
        where_data = "WHERE date(COALESCE(criado_em, data)) = date(?)"
        params.append(data_ref)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            f'''
            SELECT
                date(COALESCE(criado_em, data)) AS data_ref,
                liga,
                jogo,
                mercado,
                COUNT(*) AS total
            FROM sinais
            {where_data}
            GROUP BY data_ref, liga, jogo, mercado
            HAVING COUNT(*) > 1
            ORDER BY data_ref DESC, total DESC, liga, jogo, mercado
            ''',
            tuple(params),
        )
        rows = c.fetchall()

    out = []
    for row in rows:
        data_dup, liga, jogo, mercado, total = row
        jogo_txt = str(jogo or "")
        if " vs " in jogo_txt:
            team_home, team_away = jogo_txt.split(" vs ", 1)
        else:
            team_home, team_away = jogo_txt, ""
        out.append(
            {
                "date": str(data_dup),
                "league": str(liga or ""),
                "team_home": str(team_home).strip(),
                "team_away": str(team_away).strip(),
                "market": str(mercado or ""),
                "count": int(total or 0),
            }
        )
    return out

def atualizar_resultado(sinal_id: int, resultado: str, lucro: float) -> None:
    """
    Finaliza um sinal com resultado e lucro.
    BUG-04: UPDATE condicional  s atualiza se status ainda  'pendente'.
    Torna a operao idempotente: chamadas duplicadas no sobrescrevem
    um resultado j registrado por outra execuo concorrente.
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE sinais SET status = 'finalizado', resultado = ?, lucro_unidades = ?
            WHERE id = ? AND status = 'pendente'
        ''', (resultado, lucro, sinal_id))


def atualizar_fixture_referencia(
    sinal_id: int,
    fixture_id_api: Optional[str] = None,
    fixture_data_api: Optional[str] = None,
) -> None:
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


def verificar_status_sinal(sinal_id):
    """
    Retorna o status atual do sinal ou None se no existir.
    Usado pelo guard de dupla finalizao no settlement (BUG-04).
    Separado de sinal_existe() para permitir mock independente em testes.
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT status FROM sinais WHERE id = ? LIMIT 1", (sinal_id,))
        row = c.fetchone()
        return row[0] if row else None

def buscar_sinais_hoje() -> List[Any]:
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


def registrar_alerta_operacional(
    severidade: str,
    codigo: str,
    playbook_id: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
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


def registrar_fallback_cycle_detail(
    job_nome: str,
    janela_chave: str,
    liga: str,
    jogo: str,
    mercado: str,
    motivo_fallback: str,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    garantir_tabelas_operacionais()
    if not all([job_nome, janela_chave, liga, jogo, mercado, motivo_fallback]):
        raise ValueError("Campos obrigatorios ausentes em fallback_cycle_details")
    detalhes_json = None
    if detalhes is not None:
        detalhes_json = json.dumps(detalhes, ensure_ascii=False)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO fallback_cycle_details (
                ocorrido_em, job_nome, janela_chave, liga, jogo, mercado, motivo_fallback, detalhes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                datetime.now(UTC).isoformat(),
                job_nome,
                janela_chave,
                liga,
                jogo,
                mercado,
                motivo_fallback,
                detalhes_json,
            ),
        )


def obter_slo_disponibilidade_ciclo(dias: int = 7) -> Dict[str, Any]:
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


def registrar_shadow_prediction(
    liga: str,
    jogo: str,
    mercado: str,
    prob_baseline: Optional[float],
    prob_advanced: Optional[float],
    prediction_id_baseline: Optional[str] = None,
    prediction_id_advanced: Optional[str] = None,
    shadow_mode: bool = True,
    detalhes: Optional[Dict[str, Any]] = None,
    data_ref: Optional[str] = None,
) -> int:
    garantir_tabelas_operacionais()
    if prob_baseline is None or prob_advanced is None:
        raise ValueError("prob_baseline/prob_advanced must not be None")
    data_alvo = data_ref or datetime.now(UTC).date().isoformat()
    detalhes_json = None
    if detalhes is not None:
        detalhes_json = json.dumps(detalhes, ensure_ascii=False)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO shadow_predictions (
                ocorrido_em,
                data_ref,
                liga,
                jogo,
                mercado,
                prediction_id_baseline,
                prediction_id_advanced,
                prob_baseline,
                prob_advanced,
                shadow_mode,
                detalhes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                datetime.now(UTC).isoformat(),
                data_alvo,
                liga,
                jogo,
                mercado,
                prediction_id_baseline,
                prediction_id_advanced,
                float(prob_baseline),
                float(prob_advanced),
                1 if shadow_mode else 0,
                detalhes_json,
            ),
        )
        if c.lastrowid is None:
            raise RuntimeError("Falha ao persistir shadow_prediction: lastrowid ausente")
        return int(c.lastrowid)


def liquidar_shadow_predictions_por_sinal(
    liga: str,
    jogo: str,
    mercado: str,
    outcome: Optional[int],
    closing_odds: Optional[float] = None,
    data_ref: Optional[str] = None,
) -> int:
    """Liquida previsoes shadow pendentes para um sinal finalizado no mesmo dia."""
    data_alvo = data_ref or datetime.now(UTC).date().isoformat()
    if outcome is None:
        raise ValueError("outcome must not be None")
    out = int(outcome)
    if out not in (0, 1):
        raise ValueError("outcome must be 0 or 1")

    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT id, prob_baseline, prob_advanced
            FROM shadow_predictions
            WHERE lower(trim(liga)) = lower(trim(?))
              AND lower(trim(jogo)) = lower(trim(?))
              AND lower(trim(mercado)) = lower(trim(?))
              AND date(data_ref) = date(?)
              AND outcome IS NULL
            ''',
            (liga, jogo, mercado, data_alvo),
        )
        rows = c.fetchall()
        if not rows:
            return 0

        atualizados = 0
        for row in rows:
            pred_id = int(row[0])
            p_baseline = float(row[1] or 0.0)
            p_advanced = float(row[2] or 0.0)
            brier_baseline = (p_baseline - out) ** 2
            brier_advanced = (p_advanced - out) ** 2

            clv_baseline = None
            clv_advanced = None
            odd_close = None
            if closing_odds is not None:
                odd_close = float(closing_odds)
                # Aqui CLV proxy representa edge no fechamento (EV ao close).
                clv_baseline = (p_baseline * odd_close) - 1.0
                clv_advanced = (p_advanced * odd_close) - 1.0

            c.execute(
                '''
                UPDATE shadow_predictions
                SET outcome = ?,
                    brier_baseline = ?,
                    brier_advanced = ?,
                    closing_odds = COALESCE(?, closing_odds),
                    clv_baseline = ?,
                    clv_advanced = ?
                WHERE id = ?
                ''',
                (
                    out,
                    round(float(brier_baseline), 6),
                    round(float(brier_advanced), 6),
                    odd_close,
                    None if clv_baseline is None else round(float(clv_baseline), 6),
                    None if clv_advanced is None else round(float(clv_advanced), 6),
                    pred_id,
                ),
            )
            atualizados += 1
        return atualizados


def listar_shadow_settled_por_janela(dias=21):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT liga, mercado, brier_baseline, brier_advanced, clv_baseline, clv_advanced, ocorrido_em
            FROM shadow_predictions
            WHERE outcome IS NOT NULL
              AND brier_baseline IS NOT NULL
              AND brier_advanced IS NOT NULL
              AND ocorrido_em >= datetime('now', ?)
            ORDER BY ocorrido_em ASC
            ''',
            (f'-{int(max(1, dias))} day',),
        )
        return c.fetchall()


def upsert_blend_weight(liga, mercado, w_poisson, w_mercado, min_amostra=50, versao='v1'):
    garantir_tabelas_operacionais()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO blend_weights (liga, mercado, w_poisson, w_mercado, min_amostra, versao, gerado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(liga, mercado)
            DO UPDATE SET
                w_poisson = excluded.w_poisson,
                w_mercado = excluded.w_mercado,
                min_amostra = excluded.min_amostra,
                versao = excluded.versao,
                gerado_em = excluded.gerado_em
            ''',
            (
                liga,
                mercado,
                float(w_poisson),
                float(w_mercado),
                int(min_amostra),
                str(versao),
                datetime.now(UTC).isoformat(),
            ),
        )


def obter_blend_weight(liga, mercado):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT w_poisson, w_mercado, min_amostra, versao
            FROM blend_weights
                        WHERE ((liga = ?) OR (liga IS NULL AND ? IS NULL))
                            AND ((mercado = ?) OR (mercado IS NULL AND ? IS NULL))
            LIMIT 1
            ''',
                        (liga, liga, mercado, mercado),
        )
        row = c.fetchone()
        if row:
            return {
                'w_poisson': float(row[0]),
                'w_mercado': float(row[1]),
                'min_amostra': int(row[2] or 50),
                'versao': str(row[3] or 'v1'),
            }

        c.execute(
            '''
            SELECT w_poisson, w_mercado, min_amostra, versao
            FROM blend_weights
            WHERE liga IS NULL AND mercado IS NULL
            LIMIT 1
            '''
        )
        row = c.fetchone()
        if row:
            return {
                'w_poisson': float(row[0]),
                'w_mercado': float(row[1]),
                'min_amostra': int(row[2] or 50),
                'versao': str(row[3] or 'v1'),
            }
    return None


def registrar_walk_forward_result(fold_id, data_inicio, data_fim, brier_val, brier_test, roi_test, n_picks):
    garantir_tabelas_operacionais()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO walk_forward_results (
                fold_id, data_inicio, data_fim, brier_val, brier_test, roi_test, n_picks, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fold_id)
            DO UPDATE SET
                data_inicio = excluded.data_inicio,
                data_fim = excluded.data_fim,
                brier_val = excluded.brier_val,
                brier_test = excluded.brier_test,
                roi_test = excluded.roi_test,
                n_picks = excluded.n_picks,
                criado_em = excluded.criado_em
            ''',
            (
                str(fold_id),
                str(data_inicio),
                str(data_fim),
                None if brier_val is None else float(brier_val),
                None if brier_test is None else float(brier_test),
                None if roi_test is None else float(roi_test),
                int(n_picks or 0),
                datetime.now(UTC).isoformat(),
            ),
        )


def upsert_segment_threshold(liga, mercado, ev_floor, confidence_floor, edge_cutoff, min_amostra=50, versao='v1'):
    garantir_tabelas_operacionais()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO segment_thresholds (
                liga, mercado, ev_floor, confidence_floor, edge_cutoff, min_amostra, versao, gerado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(liga, mercado)
            DO UPDATE SET
                ev_floor = excluded.ev_floor,
                confidence_floor = excluded.confidence_floor,
                edge_cutoff = excluded.edge_cutoff,
                min_amostra = excluded.min_amostra,
                versao = excluded.versao,
                gerado_em = excluded.gerado_em
            ''',
            (
                liga,
                mercado,
                float(ev_floor),
                float(confidence_floor),
                float(edge_cutoff),
                int(min_amostra),
                str(versao),
                datetime.now(UTC).isoformat(),
            ),
        )


def obter_segment_threshold(liga, mercado):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            '''
            SELECT ev_floor, confidence_floor, edge_cutoff, min_amostra, versao
            FROM segment_thresholds
                        WHERE ((liga = ?) OR (liga IS NULL AND ? IS NULL))
                            AND ((mercado = ?) OR (mercado IS NULL AND ? IS NULL))
            LIMIT 1
            ''',
                        (liga, liga, mercado, mercado),
        )
        row = c.fetchone()
        if row:
            return {
                'ev_floor': float(row[0]),
                'confidence_floor': float(row[1]),
                'edge_cutoff': float(row[2]),
                'min_amostra': int(row[3] or 50),
                'versao': str(row[4] or 'v1'),
            }

        c.execute(
            '''
            SELECT ev_floor, confidence_floor, edge_cutoff, min_amostra, versao
            FROM segment_thresholds
            WHERE liga IS NULL AND mercado IS NULL
            LIMIT 1
            '''
        )
        row = c.fetchone()
        if row:
            return {
                'ev_floor': float(row[0]),
                'confidence_floor': float(row[1]),
                'edge_cutoff': float(row[2]),
                'min_amostra': int(row[3] or 50),
                'versao': str(row[4] or 'v1'),
            }
    return None

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
