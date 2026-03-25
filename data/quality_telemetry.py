import sqlite3
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "edge_protocol.db")
QUALITY_TABLE = "quality_trends"


def _to_date(valor):
    if isinstance(valor, date):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    return date.today()


def _janela_semanal(referencia=None):
    ref = _to_date(referencia)
    inicio = ref - timedelta(days=6)
    fim = ref
    return inicio.isoformat(), fim.isoformat(), ref.isoformat()


def garantir_tabela_quality_trends(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        f'''
        CREATE TABLE IF NOT EXISTS {QUALITY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referencia_semana TEXT NOT NULL,
            segmento_tipo TEXT NOT NULL,
            segmento_valor TEXT NOT NULL,
            total_apostas INTEGER NOT NULL,
            win_rate REAL,
            roi_pct REAL,
            brier_medio REAL,
            fallback_rate REAL DEFAULT 0.0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referencia_semana, segmento_tipo, segmento_valor)
        )
        '''
    )
    conn.commit()
    conn.close()


def _calcular_segmento(conn, data_inicio, data_fim, segmento_tipo, segmento_valor):
    c = conn.cursor()

    filtro_segmento = ""
    params_sinais = [data_inicio, data_fim]
    params_brier = [data_inicio, data_fim]

    if segmento_tipo == "mercado":
        filtro_segmento = " AND s.mercado = ?"
        params_sinais.append(segmento_valor)
        params_brier.append(segmento_valor)

    c.execute(
        f'''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN s.resultado = 'verde' THEN 1 ELSE 0 END) as vitorias,
            SUM(COALESCE(s.lucro_unidades, 0.0)) as lucro_total
        FROM sinais s
        WHERE s.status = 'finalizado'
          AND s.data BETWEEN ? AND ?
          {filtro_segmento}
        ''',
        params_sinais,
    )
    total, vitorias, lucro_total = c.fetchone() or (0, 0, 0.0)
    total = int(total or 0)
    vitorias = int(vitorias or 0)
    lucro_total = float(lucro_total or 0.0)

    c.execute(
        f'''
        SELECT AVG(bt.brier_score)
        FROM brier_tracking bt
        JOIN sinais s ON s.id = bt.sinal_id
        WHERE bt.brier_score IS NOT NULL
          AND s.data BETWEEN ? AND ?
          {filtro_segmento}
        ''',
        params_brier,
    )
    brier_avg = c.fetchone()[0]

    win_rate = round((vitorias / total), 4) if total > 0 else None
    roi_pct = round((lucro_total / total) * 100.0, 4) if total > 0 else None
    brier_medio = round(float(brier_avg), 4) if brier_avg is not None else None

    return {
        "segmento_tipo": segmento_tipo,
        "segmento_valor": segmento_valor,
        "total_apostas": total,
        "win_rate": win_rate,
        "roi_pct": roi_pct,
        "brier_medio": brier_medio,
        "fallback_rate": 0.0,
    }


def calcular_snapshot_qualidade_semanal(db_path=None, referencia=None):
    path = db_path or DB_PATH
    data_inicio, data_fim, referencia_semana = _janela_semanal(referencia)

    conn = sqlite3.connect(path)
    c = conn.cursor()

    segmentos = []
    segmentos.append(_calcular_segmento(conn, data_inicio, data_fim, "global", "all"))

    c.execute(
        '''
        SELECT DISTINCT mercado
        FROM sinais
        WHERE status = 'finalizado'
          AND data BETWEEN ? AND ?
          AND mercado IS NOT NULL
          AND mercado != ''
        ORDER BY mercado
        ''',
        (data_inicio, data_fim),
    )
    mercados = [r[0] for r in c.fetchall()]

    for mercado in mercados:
        segmentos.append(_calcular_segmento(conn, data_inicio, data_fim, "mercado", mercado))

    conn.close()

    return {
        "referencia_semana": referencia_semana,
        "periodo_inicio": data_inicio,
        "periodo_fim": data_fim,
        "segmentos": segmentos,
    }


def persistir_snapshot_qualidade(snapshot, db_path=None):
    path = db_path or DB_PATH
    garantir_tabela_quality_trends(path)
    conn = sqlite3.connect(path)
    c = conn.cursor()

    referencia = snapshot["referencia_semana"]
    segmentos = snapshot.get("segmentos", [])
    for seg in segmentos:
        c.execute(
            f'''
            INSERT INTO {QUALITY_TABLE} (
                referencia_semana,
                segmento_tipo,
                segmento_valor,
                total_apostas,
                win_rate,
                roi_pct,
                brier_medio,
                fallback_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(referencia_semana, segmento_tipo, segmento_valor)
            DO UPDATE SET
                total_apostas = excluded.total_apostas,
                win_rate = excluded.win_rate,
                roi_pct = excluded.roi_pct,
                brier_medio = excluded.brier_medio,
                fallback_rate = excluded.fallback_rate
            ''',
            (
                referencia,
                seg.get("segmento_tipo", "global"),
                seg.get("segmento_valor", "all"),
                int(seg.get("total_apostas") or 0),
                seg.get("win_rate"),
                seg.get("roi_pct"),
                seg.get("brier_medio"),
                float(seg.get("fallback_rate") or 0.0),
            ),
        )

    conn.commit()
    conn.close()


def registrar_snapshot_qualidade_semanal(db_path=None, referencia=None):
    snapshot = calcular_snapshot_qualidade_semanal(db_path=db_path, referencia=referencia)
    persistir_snapshot_qualidade(snapshot, db_path=db_path)
    return snapshot


def listar_historico_qualidade(segmento_tipo="global", segmento_valor="all", limite=12, db_path=None):
    path = db_path or DB_PATH
    garantir_tabela_quality_trends(path)
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute(
        f'''
        SELECT referencia_semana, total_apostas, win_rate, roi_pct, brier_medio, fallback_rate
        FROM {QUALITY_TABLE}
        WHERE segmento_tipo = ? AND segmento_valor = ?
        ORDER BY referencia_semana DESC
        LIMIT ?
        ''',
        (segmento_tipo, segmento_valor, int(limite)),
    )
    rows = c.fetchall()
    conn.close()

    historico = [
        {
            "referencia_semana": r[0],
            "total_apostas": int(r[1] or 0),
            "win_rate": r[2],
            "roi_pct": r[3],
            "brier_medio": r[4],
            "fallback_rate": float(r[5] or 0.0),
        }
        for r in rows
    ]
    historico.reverse()
    return historico


def avaliar_drift_historico(
    db_path=None,
    segmento_tipo="global",
    segmento_valor="all",
    janela=4,
    min_persistencia=3,
    brier_limite=0.25,
    win_rate_limite=0.50,
    fallback_limite=0.35,
):
    historico = listar_historico_qualidade(
        segmento_tipo=segmento_tipo,
        segmento_valor=segmento_valor,
        limite=janela,
        db_path=db_path,
    )
    if len(historico) < int(min_persistencia):
        return None

    janela_recente = historico[-int(min_persistencia) :]

    checks = {
        "brier_medio": all(
            item.get("brier_medio") is not None and float(item.get("brier_medio")) >= float(brier_limite)
            for item in janela_recente
        ),
        "win_rate": all(
            item.get("win_rate") is not None and float(item.get("win_rate")) <= float(win_rate_limite)
            for item in janela_recente
        ),
        "fallback_rate": all(
            float(item.get("fallback_rate") or 0.0) >= float(fallback_limite)
            for item in janela_recente
        ),
    }

    metrica = None
    if checks["brier_medio"]:
        metrica = "brier_medio"
    elif checks["win_rate"]:
        metrica = "win_rate"
    elif checks["fallback_rate"]:
        metrica = "fallback_rate"

    if not metrica:
        return None

    ultimo = janela_recente[-1]
    return {
        "alerta": True,
        "metrica": metrica,
        "segmento_tipo": segmento_tipo,
        "segmento_valor": segmento_valor,
        "min_persistencia": int(min_persistencia),
        "janela_avaliada": int(janela),
        "periodo_inicio": janela_recente[0]["referencia_semana"],
        "periodo_fim": janela_recente[-1]["referencia_semana"],
        "valor_atual": ultimo.get(metrica),
        "limites": {
            "brier_medio": float(brier_limite),
            "win_rate": float(win_rate_limite),
            "fallback_rate": float(fallback_limite),
        },
    }
