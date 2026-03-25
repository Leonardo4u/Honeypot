from __future__ import annotations

import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, "data", "edge_protocol.db")


def main() -> int:
    if not os.path.exists(DB_PATH):
        print("[promotion] banco nao encontrado; gate ignorado.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT promotion_pass, summary_json
            FROM backtest_runs
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()

    if not row:
        print("[promotion] sem backtest registrado; gate ignorado.")
        return 0

    passed = bool(row[0])
    summary = row[1] or "{}"
    print(f"[promotion] status={'PASS' if passed else 'FAIL'}")
    try:
        print(summary)
        parsed = json.loads(summary)
        reasons = parsed.get("promotion", {}).get("reasons", [])
    except Exception:
        reasons = []

    if not passed:
        if any(r.startswith("amostra_insuficiente") for r in reasons):
            print("[promotion] sem amostra minima; gate informativo (nao bloqueante).")
            return 0
        print(f"[promotion] bloqueado: {','.join(reasons) if reasons else 'motivo_indefinido'}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
