# pip install flask pandas

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "edge_protocol.db"

app = Flask(__name__)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _to_date(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _dict_rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _run_query(conn: sqlite3.Connection, sql: str, params=None, debug=False, tag="sql"):
    params = params or []
    if debug:
        print(f"[DEBUG:{tag}] {sql.strip()}")
        print(f"[DEBUG:{tag}:params] {params}")
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def _empty_payload_dados(ligas=None):
    return {
        "kpis": {
            "total_sinais": 0,
            "winrate": 0.0,
            "roi": 0.0,
            "clv_medio": 0.0,
            "brier_medio": 0.0,
            "ultimo_ciclo": None,
            "delta_7d": {
                "total_sinais": 0.0,
                "winrate": 0.0,
                "roi": 0.0,
                "clv_medio": 0.0,
                "brier_medio": 0.0,
            },
        },
        "grafico_lucro": [],
        "winrate_por_liga": [],
        "edges_hist": {"bins": [], "counts": []},
        "clv_por_semana": [],
        "sinais": [],
        "pagination": {"page": 1, "per_page": 25, "total": 0, "total_pages": 0},
        "ligas": ligas or [],
    }


def _build_filters(liga: str | None, status: str | None, busca: str | None):
    clauses = []
    params = []

    if liga:
        clauses.append("s.liga = ?")
        params.append(liga)

    if status and status != "todos":
        clauses.append("s.status = ?")
        params.append(status)

    if busca:
        clauses.append("lower(s.jogo) LIKE ?")
        params.append(f"%{busca.strip().lower()}%")

    if not clauses:
        return "", params

    return " WHERE " + " AND ".join(clauses) + " ", params


def _fetch_ligas(conn):
    if not _table_exists(conn, "sinais"):
        return []
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT liga FROM sinais WHERE liga IS NOT NULL AND liga != '' ORDER BY liga")
    return [r[0] for r in cur.fetchall()]


def _compute_kpis(conn, where_sql, params, debug=False):
    query = f"""
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN resultado='verde' THEN 1 ELSE 0 END) * 100.0 /
              NULLIF(SUM(CASE WHEN resultado IN ('verde','vermelho') THEN 1 ELSE 0 END),0) as winrate,
          SUM(lucro_unidades) /
              NULLIF(SUM(CASE WHEN resultado IN ('verde','vermelho') THEN 1 ELSE 0 END),0) * 100 as roi
        FROM sinais s
        {where_sql}
    """
    cur = _run_query(conn, query, params, debug=debug, tag="kpi_base")
    row = cur.fetchone() or (0, 0.0, 0.0)

    clv_avg = 0.0
    if _table_exists(conn, "clv_tracking"):
        clv_q = f"""
            SELECT AVG(ct.clv_percentual)
            FROM clv_tracking ct
            JOIN sinais s ON s.id = ct.sinal_id
            {where_sql}
        """
        cur = _run_query(conn, clv_q, params, debug=debug, tag="kpi_clv")
        clv_avg = _safe_float((cur.fetchone() or [0.0])[0], 0.0)

    brier_avg = 0.0
    if _table_exists(conn, "brier_tracking"):
        brier_q = f"""
            SELECT AVG(bt.brier_score)
            FROM brier_tracking bt
            JOIN sinais s ON s.id = bt.sinal_id
            {where_sql}
        """
        cur = _run_query(conn, brier_q, params, debug=debug, tag="kpi_brier")
        brier_avg = _safe_float((cur.fetchone() or [0.0])[0], 0.0)

    # Delta 7d vs 7d anterior
    delta = {
        "total_sinais": 0.0,
        "winrate": 0.0,
        "roi": 0.0,
        "clv_medio": 0.0,
        "brier_medio": 0.0,
    }

    base_hist_q = f"""
        SELECT date(data) AS d, COUNT(*) AS total,
               SUM(CASE WHEN resultado='verde' THEN 1 ELSE 0 END) AS verdes,
               SUM(CASE WHEN resultado IN ('verde','vermelho') THEN 1 ELSE 0 END) AS liquidados,
               SUM(COALESCE(lucro_unidades, 0.0)) AS lucro
        FROM sinais s
        {where_sql}
        GROUP BY date(data)
        ORDER BY d
    """
    cur = _run_query(conn, base_hist_q, params, debug=debug, tag="kpi_delta")
    hist_rows = _dict_rows(cur)

    if hist_rows:
        df = pd.DataFrame(hist_rows)
        df["d"] = pd.to_datetime(df["d"], errors="coerce")
        df = df.dropna(subset=["d"]).sort_values("d")
        if not df.empty:
            last_day = df["d"].max()
            start_7 = last_day - pd.Timedelta(days=6)
            prev_start = start_7 - pd.Timedelta(days=7)
            prev_end = start_7 - pd.Timedelta(days=1)

            cur_df = df[(df["d"] >= start_7) & (df["d"] <= last_day)]
            prv_df = df[(df["d"] >= prev_start) & (df["d"] <= prev_end)]

            def _metrics(frame):
                total = int(frame["total"].sum()) if not frame.empty else 0
                verdes = _safe_float(frame["verdes"].sum(), 0.0) if not frame.empty else 0.0
                liq = _safe_float(frame["liquidados"].sum(), 0.0) if not frame.empty else 0.0
                lucro = _safe_float(frame["lucro"].sum(), 0.0) if not frame.empty else 0.0
                win = (verdes / liq * 100.0) if liq > 0 else 0.0
                roi = (lucro / liq * 100.0) if liq > 0 else 0.0
                return {"total": total, "winrate": win, "roi": roi}

            m_cur = _metrics(cur_df)
            m_prv = _metrics(prv_df)

            delta["total_sinais"] = round(m_cur["total"] - m_prv["total"], 2)
            delta["winrate"] = round(m_cur["winrate"] - m_prv["winrate"], 2)
            delta["roi"] = round(m_cur["roi"] - m_prv["roi"], 2)

    ultimo_ciclo = None
    cur = _run_query(conn, "SELECT MAX(data) FROM sinais", debug=debug, tag="ultimo_ciclo")
    val = cur.fetchone()
    if val:
        ultimo_ciclo = val[0]

    return {
        "total_sinais": _safe_int(row[0], 0),
        "winrate": round(_safe_float(row[1], 0.0), 2),
        "roi": round(_safe_float(row[2], 0.0), 2),
        "clv_medio": round(clv_avg, 2),
        "brier_medio": round(brier_avg, 4),
        "ultimo_ciclo": ultimo_ciclo,
        "delta_7d": delta,
    }


def _grafico_lucro(conn, where_sql, params, debug=False):
    q = f"""
        SELECT date(data) as dia, SUM(lucro_unidades) as lucro_dia
        FROM sinais s
        {where_sql}
          {'AND' if where_sql else 'WHERE'} resultado IN ('verde','vermelho')
        GROUP BY date(data)
        ORDER BY dia
    """
    cur = _run_query(conn, q, params, debug=debug, tag="grafico_lucro")
    rows = _dict_rows(cur)
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["lucro_dia"] = pd.to_numeric(df["lucro_dia"], errors="coerce").fillna(0.0)
    df["lucro_acumulado"] = df["lucro_dia"].cumsum()

    return [
        {
            "data": str(r["dia"]),
            "lucro_acumulado": round(float(r["lucro_acumulado"]), 4),
        }
        for _, r in df.iterrows()
    ]


def _winrate_por_liga(conn, where_sql, params, debug=False):
    q = f"""
        SELECT liga,
          SUM(CASE WHEN resultado='verde' THEN 1 ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN resultado IN ('verde','vermelho') THEN 1 END),0) as winrate
        FROM sinais s
        {where_sql}
        GROUP BY liga
        ORDER BY winrate DESC
        LIMIT 10
    """
    cur = _run_query(conn, q, params, debug=debug, tag="winrate_liga")
    rows = _dict_rows(cur)
    out = []
    for r in rows:
        if r.get("liga") is None:
            continue
        out.append({"liga": str(r["liga"]), "winrate": round(_safe_float(r["winrate"], 0.0), 2)})
    return out


def _edges_histograma(conn, where_sql, params, debug=False):
    q = f"""
        SELECT edge_score
        FROM sinais s
        {where_sql}
          {'AND' if where_sql else 'WHERE'} edge_score IS NOT NULL
    """
    cur = _run_query(conn, q, params, debug=debug, tag="edges_hist")
    values = [_safe_float(r[0], 0.0) for r in cur.fetchall()]
    if not values:
        return {"bins": [], "counts": []}

    bins = list(range(0, 105, 5))
    counts = [0] * (len(bins) - 1)
    for v in values:
        idx = min(int(max(v, 0) // 5), len(counts) - 1)
        counts[idx] += 1

    labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(counts))]
    return {"bins": labels, "counts": counts}


def _clv_por_semana(conn, where_sql, params, debug=False):
    if not _table_exists(conn, "clv_tracking"):
        return []
    q = f"""
        SELECT strftime('%Y-%W', s.data) AS semana, AVG(ct.clv_percentual) AS clv_medio
        FROM clv_tracking ct
        JOIN sinais s ON s.id = ct.sinal_id
        {where_sql}
        GROUP BY strftime('%Y-%W', s.data)
        ORDER BY semana
    """
    cur = _run_query(conn, q, params, debug=debug, tag="clv_semana")
    return [
        {"semana": str(r[0]), "clv_medio": round(_safe_float(r[1], 0.0), 3)}
        for r in cur.fetchall()
    ]


def _fetch_sinais(conn, where_sql, params, page, per_page, debug=False):
    total_q = f"SELECT COUNT(*) FROM sinais s {where_sql}"
    cur = _run_query(conn, total_q, params, debug=debug, tag="sinais_total")
    total = _safe_int((cur.fetchone() or [0])[0], 0)

    offset = (page - 1) * per_page
    data_q = f"""
        SELECT
            s.id, s.data, s.liga, s.jogo, s.mercado, s.odd, s.ev_estimado,
            s.edge_score, s.status, s.resultado, s.lucro_unidades,
            ct.clv_percentual
        FROM sinais s
        LEFT JOIN clv_tracking ct ON ct.sinal_id = s.id
        {where_sql}
        ORDER BY date(s.data) DESC, s.id DESC
        LIMIT ? OFFSET ?
    """
    cur = _run_query(conn, data_q, [*params, per_page, offset], debug=debug, tag="sinais_page")
    rows = _dict_rows(cur)

    sinais = []
    for r in rows:
        sinais.append(
            {
                "id": _safe_int(r.get("id"), 0),
                "data": str(r.get("data") or ""),
                "liga": str(r.get("liga") or ""),
                "jogo": str(r.get("jogo") or ""),
                "mercado": str(r.get("mercado") or ""),
                "odd": round(_safe_float(r.get("odd"), 0.0), 2),
                "edge_score": round(_safe_float(r.get("edge_score"), 0.0), 2),
                "ev_estimado": round(_safe_float(r.get("ev_estimado"), 0.0) * 100.0, 2),
                "status": str(r.get("status") or ""),
                "resultado": str(r.get("resultado") or ""),
                "lucro_unidades": round(_safe_float(r.get("lucro_unidades"), 0.0), 4),
                "clv_percentual": round(_safe_float(r.get("clv_percentual"), 0.0), 3),
            }
        )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return sinais, {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


def _calibration_payload(conn, debug=False):
    payload = {
        "reliability_curve": [],
        "brier_por_mercado": [],
        "clv_por_semana": [],
        "shadow_vs_real": [],
        "ece": 0.0,
        "mce": 0.0,
        "calibration_label": "Sem dados",
    }

    if not _table_exists(conn, "sinais"):
        return payload

    # Reliability curve usando ev_estimado como probabilidade predita.
    rel_q = """
        SELECT ev_estimado, resultado
        FROM sinais
        WHERE resultado IN ('verde', 'vermelho')
          AND ev_estimado IS NOT NULL
    """
    cur = _run_query(conn, rel_q, debug=debug, tag="cal_rel")
    rows = cur.fetchall()

    if rows:
        df = pd.DataFrame(rows, columns=["ev", "resultado"])
        df["p"] = pd.to_numeric(df["ev"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
        df["y"] = (df["resultado"] == "verde").astype(int)
        df["bin"] = (df["p"] * 10).astype(int).clip(0, 9)

        total_n = len(df)
        ece = 0.0
        mce = 0.0
        rel_points = []
        for b in range(10):
            part = df[df["bin"] == b]
            if part.empty:
                rel_points.append(
                    {
                        "bin": round((b + 0.5) / 10.0, 2),
                        "pred": round((b + 0.5) / 10.0, 2),
                        "obs": None,
                        "n": 0,
                    }
                )
                continue

            pred = float(part["p"].mean())
            obs = float(part["y"].mean())
            gap = abs(pred - obs)
            w = len(part) / total_n
            ece += w * gap
            mce = max(mce, gap)
            rel_points.append(
                {
                    "bin": round((b + 0.5) / 10.0, 2),
                    "pred": round(pred, 4),
                    "obs": round(obs, 4),
                    "n": int(len(part)),
                }
            )

        payload["reliability_curve"] = rel_points
        payload["ece"] = round(float(ece), 6)
        payload["mce"] = round(float(mce), 6)

        if ece < 0.05:
            payload["calibration_label"] = "Bem calibrado"
        elif ece < 0.10:
            payload["calibration_label"] = "Calibracao aceitavel"
        else:
            payload["calibration_label"] = "Calibracao fraca"

    if _table_exists(conn, "brier_tracking"):
        brier_q = """
            SELECT s.mercado, AVG(bt.brier_score) AS brier
            FROM brier_tracking bt
            JOIN sinais s ON s.id = bt.sinal_id
            WHERE bt.brier_score IS NOT NULL
            GROUP BY s.mercado
            ORDER BY s.mercado
        """
        cur = _run_query(conn, brier_q, debug=debug, tag="cal_brier_market")
        payload["brier_por_mercado"] = [
            {"mercado": str(r[0]), "brier": round(_safe_float(r[1], 0.0), 4)}
            for r in cur.fetchall()
        ]

    if _table_exists(conn, "clv_tracking"):
        clv_q = """
            SELECT strftime('%Y-%W', s.data) AS semana, AVG(ct.clv_percentual) AS clv_medio
            FROM clv_tracking ct
            JOIN sinais s ON s.id = ct.sinal_id
            WHERE ct.clv_percentual IS NOT NULL
            GROUP BY strftime('%Y-%W', s.data)
            ORDER BY semana
        """
        cur = _run_query(conn, clv_q, debug=debug, tag="cal_clv_semana")
        payload["clv_por_semana"] = [
            {"semana": str(r[0]), "clv_medio": round(_safe_float(r[1], 0.0), 3)}
            for r in cur.fetchall()
        ]

    if _table_exists(conn, "shadow_predictions"):
        sh_q = """
            SELECT
                liga,
                mercado,
                COUNT(*) AS shadow_total,
                SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) AS shadow_settled,
                AVG(brier_baseline) AS brier_baseline_avg,
                AVG(brier_advanced) AS brier_advanced_avg
            FROM shadow_predictions
            GROUP BY liga, mercado
            HAVING SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) > 0
            ORDER BY shadow_settled DESC, liga, mercado
        """
        cur = _run_query(conn, sh_q, debug=debug, tag="cal_shadow")
        payload["shadow_vs_real"] = [
            {
                "liga": str(r[0]),
                "mercado": str(r[1]),
                "shadow_total": _safe_int(r[2], 0),
                "shadow_settled": _safe_int(r[3], 0),
                "brier_baseline_avg": round(_safe_float(r[4], 0.0), 4),
                "brier_advanced_avg": round(_safe_float(r[5], 0.0), 4),
            }
            for r in cur.fetchall()
        ]

    return payload


def _health_payload(conn, debug=False):
    payload = {
        "odds_api": {"ok": False, "ultima_coleta": None},
        "api_football": {"ok": False, "ultimo_resultado": None},
    }

    if not _table_exists(conn, "sinais"):
        return payload

    q1 = "SELECT MAX(data) as ultima_coleta FROM sinais"
    q2 = "SELECT MAX(data) as ultimo_resultado FROM sinais WHERE status='finalizado'"

    cur = _run_query(conn, q1, debug=debug, tag="health_odds")
    ultima = (cur.fetchone() or [None])[0]
    cur = _run_query(conn, q2, debug=debug, tag="health_result")
    ultimo_result = (cur.fetchone() or [None])[0]

    today = datetime.utcnow().date()
    d1 = _to_date(ultima)
    d2 = _to_date(ultimo_result)

    payload["odds_api"] = {
        "ok": bool(d1 and (today - d1).days <= 1),
        "ultima_coleta": ultima,
    }
    payload["api_football"] = {
        "ok": bool(d2 and (today - d2).days <= 2),
        "ultimo_resultado": ultimo_result,
    }
    return payload


def _dados_payload(liga, status, busca, page, per_page, debug=False):
    if not DB_PATH.exists():
        return _empty_payload_dados()

    conn = sqlite3.connect(DB_PATH)
    try:
        if not _table_exists(conn, "sinais"):
            return _empty_payload_dados(ligas=[])

        where_sql, params = _build_filters(liga, status, busca)
        ligas = _fetch_ligas(conn)
        kpis = _compute_kpis(conn, where_sql, params, debug=debug)
        grafico_lucro = _grafico_lucro(conn, where_sql, params, debug=debug)
        winrate_liga = _winrate_por_liga(conn, where_sql, params, debug=debug)
        edges_hist = _edges_histograma(conn, where_sql, params, debug=debug)
        clv_semana = _clv_por_semana(conn, where_sql, params, debug=debug)
        sinais, pagination = _fetch_sinais(conn, where_sql, params, page, per_page, debug=debug)

        payload = {
            "kpis": kpis,
            "grafico_lucro": grafico_lucro,
            "winrate_por_liga": winrate_liga,
            "edges_hist": edges_hist,
            "clv_por_semana": clv_semana,
            "sinais": sinais,
            "pagination": pagination,
            "ligas": ligas,
        }
        return payload
    finally:
        conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/calibracao")
def calibracao_page():
    return render_template("calibration.html")


@app.route("/api/dados")
def api_dados():
    try:
        liga = request.args.get("liga") or None
        status = request.args.get("status") or "todos"
        busca = request.args.get("q") or None
        page = max(1, _safe_int(request.args.get("page"), 1))
        per_page = max(1, min(200, _safe_int(request.args.get("per_page"), 25)))
        debug = request.args.get("debug") == "1"

        payload = _dados_payload(liga, status, busca, page, per_page, debug=debug)
        return jsonify(payload)
    except Exception as exc:
        print(f"[api_dados] erro: {exc}")
        return jsonify(_empty_payload_dados())


@app.route("/api/calibracao")
def api_calibracao():
    try:
        debug = request.args.get("debug") == "1"
        if not DB_PATH.exists():
            return jsonify(_calibration_payload(sqlite3.connect(":memory:"), debug=debug))

        conn = sqlite3.connect(DB_PATH)
        try:
            payload = _calibration_payload(conn, debug=debug)
            return jsonify(payload)
        finally:
            conn.close()
    except Exception as exc:
        print(f"[api_calibracao] erro: {exc}")
        return jsonify(
            {
                "reliability_curve": [],
                "brier_por_mercado": [],
                "clv_por_semana": [],
                "shadow_vs_real": [],
                "ece": 0.0,
                "mce": 0.0,
                "calibration_label": "Sem dados",
            }
        )


@app.route("/api/health")
def api_health():
    try:
        debug = request.args.get("debug") == "1"
        if not DB_PATH.exists():
            return jsonify(
                {
                    "odds_api": {"ok": False, "ultima_coleta": None},
                    "api_football": {"ok": False, "ultimo_resultado": None},
                }
            )

        conn = sqlite3.connect(DB_PATH)
        try:
            return jsonify(_health_payload(conn, debug=debug))
        finally:
            conn.close()
    except Exception as exc:
        print(f"[api_health] erro: {exc}")
        return jsonify(
            {
                "odds_api": {"ok": False, "ultima_coleta": None},
                "api_football": {"ok": False, "ultimo_resultado": None},
            }
        )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5050)
