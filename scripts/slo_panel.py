from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, UTC

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, "data", "edge_protocol.db")
OUT_JSON = os.path.join(ROOT, "logs", "slo_panel_latest.json")


def fetch_job_stats(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT job_nome, status, started_at, finished_at, reason_code
        FROM job_execucoes
        WHERE started_at >= datetime('now', ?)
        ORDER BY started_at DESC
        """,
        (f"-{days} day",),
    )
    rows = cur.fetchall()
    data = []
    for job_nome, status, started_at, finished_at, reason_code in rows:
        data.append(
            {
                "job_nome": job_nome,
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "reason_code": reason_code,
            }
        )
    return data


def fetch_quality(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT referencia_semana, segmento_tipo, segmento_valor, total_apostas, win_rate, roi_pct, brier_medio, fallback_rate
            FROM quality_trends
            ORDER BY referencia_semana DESC
            LIMIT 24
            """
        )
    except sqlite3.OperationalError:
        return []
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "referencia_semana": r[0],
                "segmento_tipo": r[1],
                "segmento_valor": r[2],
                "total_apostas": r[3],
                "win_rate": r[4],
                "roi_pct": r[5],
                "brier_medio": r[6],
                "fallback_rate": r[7],
            }
        )
    return out


def main() -> int:
    if not os.path.exists(DB_PATH):
        print("[slo_panel] banco nao encontrado.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "jobs_30d": fetch_job_stats(conn, days=30),
        "quality_weekly": fetch_quality(conn),
    }
    conn.close()

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)

    print(f"[slo_panel] wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
