from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, UTC

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, "data", "edge_protocol.db")
WINDOW_DAYS = int(os.getenv("EDGE_BACKTEST_WINDOW_DAYS", "28"))
MIN_SIGNALS = int(os.getenv("EDGE_BACKTEST_MIN_SIGNALS", "30"))
EDGE_VERSION = os.getenv("EDGE_VERSION", "dev")


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            app_version TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            prev_window_start TEXT,
            prev_window_end TEXT,
            total_signals INTEGER NOT NULL,
            roi_pct REAL,
            win_rate REAL,
            clv_medio REAL,
            brier_medio REAL,
            promotion_pass INTEGER NOT NULL,
            summary_json TEXT
        )
        """
    )


def metrics_for_window(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(COALESCE(s.lucro_unidades, 0)) AS lucro,
            SUM(CASE WHEN s.resultado = 'verde' THEN 1 ELSE 0 END) AS vitorias,
            AVG(bt.brier_score) AS brier,
            AVG(ct.clv_percentual) AS clv
        FROM sinais s
        LEFT JOIN brier_tracking bt ON bt.sinal_id = s.id
        LEFT JOIN clv_tracking ct ON ct.sinal_id = s.id
        WHERE s.status = 'finalizado'
          AND s.data BETWEEN ? AND ?
        """,
        (start_date, end_date),
    )
    total, lucro, vitorias, brier, clv = cur.fetchone() or (0, 0.0, 0, None, None)
    total = int(total or 0)
    lucro = float(lucro or 0.0)
    vitorias = int(vitorias or 0)
    roi_pct = round((lucro / total) * 100.0, 4) if total > 0 else None
    win_rate = round((vitorias / total), 4) if total > 0 else None
    return {
        "total": total,
        "lucro": round(lucro, 4),
        "roi_pct": roi_pct,
        "win_rate": win_rate,
        "brier_medio": round(float(brier), 4) if brier is not None else None,
        "clv_medio": round(float(clv), 4) if clv is not None else None,
    }


def evaluate_promotion(metrics: dict) -> tuple[int, list[str]]:
    roi_min = float(os.getenv("EDGE_PROMOTION_MIN_ROI_PCT", "0.5"))
    win_min = float(os.getenv("EDGE_PROMOTION_MIN_WIN_RATE", "0.5"))
    brier_max = float(os.getenv("EDGE_PROMOTION_MAX_BRIER", "0.25"))
    clv_min = float(os.getenv("EDGE_PROMOTION_MIN_CLV", "0.0"))
    reasons: list[str] = []

    if metrics["total"] < MIN_SIGNALS:
        reasons.append(f"amostra_insuficiente<{MIN_SIGNALS}")
        return 0, reasons

    if metrics.get("roi_pct") is None or metrics["roi_pct"] < roi_min:
        reasons.append("roi_abaixo_envelope")
    if metrics.get("win_rate") is None or metrics["win_rate"] < win_min:
        reasons.append("win_rate_abaixo_envelope")
    if metrics.get("brier_medio") is None or metrics["brier_medio"] > brier_max:
        reasons.append("brier_acima_envelope")
    if metrics.get("clv_medio") is None or metrics["clv_medio"] < clv_min:
        reasons.append("clv_abaixo_envelope")

    return (1 if not reasons else 0), reasons


def main() -> int:
    if not os.path.exists(DB_PATH):
        print("[backtest] banco nao encontrado; ignorando.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    end = datetime.now(UTC).date()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=WINDOW_DAYS - 1)

    atual = metrics_for_window(conn, start.isoformat(), end.isoformat())
    anterior = metrics_for_window(conn, prev_start.isoformat(), prev_end.isoformat())
    promotion_pass, reasons = evaluate_promotion(atual)

    summary = {
        "window_days": WINDOW_DAYS,
        "current": atual,
        "previous": anterior,
        "delta": {
            "roi_pct": None if atual["roi_pct"] is None or anterior["roi_pct"] is None else round(atual["roi_pct"] - anterior["roi_pct"], 4),
            "win_rate": None if atual["win_rate"] is None or anterior["win_rate"] is None else round(atual["win_rate"] - anterior["win_rate"], 4),
            "brier_medio": None if atual["brier_medio"] is None or anterior["brier_medio"] is None else round(atual["brier_medio"] - anterior["brier_medio"], 4),
            "clv_medio": None if atual["clv_medio"] is None or anterior["clv_medio"] is None else round(atual["clv_medio"] - anterior["clv_medio"], 4),
        },
        "promotion": {
            "pass": bool(promotion_pass),
            "reasons": reasons,
        },
    }

    conn.execute(
        """
        INSERT INTO backtest_runs (
            run_at, app_version, window_start, window_end, prev_window_start, prev_window_end,
            total_signals, roi_pct, win_rate, clv_medio, brier_medio, promotion_pass, summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(UTC).isoformat(),
            EDGE_VERSION,
            start.isoformat(),
            end.isoformat(),
            prev_start.isoformat(),
            prev_end.isoformat(),
            int(atual["total"]),
            atual["roi_pct"],
            atual["win_rate"],
            atual["clv_medio"],
            atual["brier_medio"],
            int(promotion_pass),
            json.dumps(summary, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()

    print("[backtest] run registrado")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
