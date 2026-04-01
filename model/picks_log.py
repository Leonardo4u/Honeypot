"""Persistencia de picks para monitoramento de calibracao e performance."""

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Optional


class PickLogger:
    """Logger CSV de um registro por pick analisado."""

    FIELDNAMES = [
        "prediction_id",
        "timestamp",
        "league",
        "market",
        "team_home",
        "team_away",
        "odds_at_pick",
        "implied_prob",
        "raw_prob_model",
        "calibrated_prob_model",
        "calibrator_fitted",
        "confidence_dados",
        "estabilidade_odd",
        "contexto_jogo",
        "edge_score",
        "kelly_fraction",
        "kelly_stake",
        "bank_used",
        "recomendacao_acao",
        "gate_reason",
        "outcome",
        "closing_odds",
    ]

    def __init__(self, csv_path: str):
        """Inicializa logger e garante arquivo CSV com cabecalho."""
        self.csv_path = csv_path
        self._ensure_csv()

    def _ensure_csv(self):
        """Garante que o arquivo exista com cabecalho padrao."""
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if os.path.exists(self.csv_path):
            return
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()

    @staticmethod
    def split_match_teams(match_name: str) -> tuple[str, str]:
        """Extrai (home, away) a partir de string de jogo."""
        raw = (match_name or "").strip()
        for sep in (" vs ", " VS ", " x ", " X "):
            if sep in raw:
                parts = raw.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return raw, ""

    @staticmethod
    def _gate_reason_from_trace(reasoning_trace: dict) -> str:
        """Consolida motivo de gate/skip a partir do trace."""
        if not isinstance(reasoning_trace, dict):
            return ""
        gate = reasoning_trace.get("gate_discard")
        if isinstance(gate, list) and gate:
            return "|".join(str(x) for x in gate)
        discarded = reasoning_trace.get("fatores_descartados")
        if isinstance(discarded, list) and discarded:
            return "|".join(str(x) for x in discarded)
        return str(reasoning_trace.get("justificativa", ""))

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[datetime]:
        """Converte timestamp textual para datetime timezone-aware em UTC."""
        raw = (value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _read_rows(self) -> list[dict]:
        """Le todas as linhas do CSV de picks."""
        self._ensure_csv()
        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _write_rows(self, rows: list[dict]):
        """Escreve o conjunto completo de linhas no CSV de picks."""
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def append_pick(
        self,
        *,
        prediction_id: str,
        league: str,
        market: str,
        match_name: str,
        odds_at_pick: float,
        implied_prob: float,
        raw_prob_model: float,
        calibrated_prob_model: float,
        calibrator_fitted: bool,
        confidence_dados: float,
        estabilidade_odd: float,
        contexto_jogo: float,
        edge_score: float,
        kelly_fraction: float,
        kelly_stake: float,
        bank_used: float,
        recomendacao_acao: str,
        reasoning_trace: Optional[dict],
    ):
        """Anexa uma linha de pick no CSV."""
        home, away = self.split_match_teams(match_name)
        row = {
            "prediction_id": prediction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "league": league,
            "market": market,
            "team_home": home,
            "team_away": away,
            "odds_at_pick": float(odds_at_pick),
            "implied_prob": float(implied_prob),
            "raw_prob_model": float(raw_prob_model),
            "calibrated_prob_model": float(calibrated_prob_model),
            "calibrator_fitted": bool(calibrator_fitted),
            "confidence_dados": float(confidence_dados),
            "estabilidade_odd": float(estabilidade_odd),
            "contexto_jogo": float(contexto_jogo),
            "edge_score": float(edge_score),
            "kelly_fraction": float(kelly_fraction),
            "kelly_stake": float(kelly_stake),
            "bank_used": float(bank_used),
            "recomendacao_acao": str(recomendacao_acao),
            "gate_reason": self._gate_reason_from_trace(reasoning_trace or {}),
            "outcome": "",
            "closing_odds": "",
        }
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writerow(row)

    def update_outcome(self, prediction_id: str, outcome: int, closing_odds: Optional[float]):
        """Atualiza outcome e closing_odds de um prediction_id ja registrado."""
        if outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")

        updated = False
        rows = self._read_rows()
        for row in rows:
            if row.get("prediction_id") == prediction_id:
                row["outcome"] = str(int(outcome))
                row["closing_odds"] = "" if closing_odds is None else str(float(closing_odds))
                updated = True

        if not updated:
            return False

        self._write_rows(rows)
        return True

    @staticmethod
    def _map_resultado_to_outcome(resultado: str) -> Optional[int]:
        """Mapeia resultado textual do banco para outcome binario do picks_log."""
        val = str(resultado or "").strip().lower()
        if val in {"verde", "win", "won", "green", "acerto", "vitoria", "vitória", "1"}:
            return 1
        if val in {"vermelho", "loss", "lost", "red", "erro", "derrota", "0"}:
            return 0
        return None

    def sync_from_db(self, db_path: str, timestamp_tolerance_seconds: int = 60) -> dict:
        """Sincroniza outcomes finalizados de `sinais` para `picks_log.csv`."""
        rows = self._read_rows()
        if not rows:
            return {"updated": 0, "matched": 0, "unmatched": 0, "total_finalizados": 0}

        by_prediction_id = {}
        by_tuple = {}
        for idx, row in enumerate(rows):
            pid = str(row.get("prediction_id") or "").strip()
            if pid:
                by_prediction_id[pid] = idx
            key = (
                str(row.get("league") or "").strip().lower(),
                str(row.get("team_home") or "").strip().lower(),
                str(row.get("team_away") or "").strip().lower(),
            )
            by_tuple.setdefault(key, []).append(idx)

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(sinais)")
            colunas = {str(r[1]) for r in cur.fetchall()}
            if "prediction_id" in colunas:
                prediction_select = "prediction_id"
            else:
                prediction_select = "NULL AS prediction_id"

            ts_cols = [c for c in ("horario", "criado_em", "data") if c in colunas]
            if ts_cols:
                ts_select = "COALESCE(" + ", ".join(ts_cols) + ") AS ts_ref"
            else:
                ts_select = "NULL AS ts_ref"

            cur.execute(
                f"""
                SELECT
                    id,
                    liga,
                    jogo,
                    resultado,
                    odd,
                    {prediction_select},
                                        {ts_select}
                FROM sinais
                WHERE status = 'finalizado'
                  AND resultado IS NOT NULL
                """
            )
            finais = cur.fetchall()
        finally:
            conn.close()

        matched = 0
        updated = 0
        unmatched = 0

        for row_db in finais:
            sinal_id, liga, jogo, resultado, odd_db, prediction_id_db, ts_ref = row_db
            outcome = self._map_resultado_to_outcome(resultado)
            if outcome is None:
                unmatched += 1
                print(
                    f"[picks_log.sync] sinal_id={sinal_id} sem mapeamento de resultado={resultado!r}",
                    file=sys.stderr,
                )
                continue

            chosen_idx = None
            pid_db = str(prediction_id_db or "").strip()
            if pid_db and pid_db in by_prediction_id:
                chosen_idx = by_prediction_id[pid_db]
            else:
                home, away = self.split_match_teams(str(jogo or ""))
                key = (
                    str(liga or "").strip().lower(),
                    home.strip().lower(),
                    away.strip().lower(),
                )
                candidates = by_tuple.get(key, [])
                if candidates:
                    ts_db = self._parse_timestamp(str(ts_ref or ""))
                    if ts_db is None:
                        chosen_idx = candidates[0]
                    else:
                        best_idx = None
                        best_delta = None
                        for c_idx in candidates:
                            ts_csv = self._parse_timestamp(rows[c_idx].get("timestamp", ""))
                            if ts_csv is None:
                                continue
                            delta = abs((ts_db - ts_csv).total_seconds())
                            if best_delta is None or delta < best_delta:
                                best_delta = delta
                                best_idx = c_idx
                        if best_idx is not None and best_delta <= float(timestamp_tolerance_seconds):
                            chosen_idx = best_idx

            if chosen_idx is None:
                unmatched += 1
                print(
                    f"[picks_log.sync] sinal_id={sinal_id} sem match (prediction_id ou tuple+tempo)",
                    file=sys.stderr,
                )
                continue

            matched += 1
            r = rows[chosen_idx]
            before_outcome = str(r.get("outcome") or "").strip()
            before_closing = str(r.get("closing_odds") or "").strip()
            r["outcome"] = str(int(outcome))
            r["closing_odds"] = "" if odd_db is None else str(float(odd_db))
            if before_outcome != r["outcome"] or before_closing != r["closing_odds"]:
                updated += 1

        self._write_rows(rows)
        return {
            "updated": updated,
            "matched": matched,
            "unmatched": unmatched,
            "total_finalizados": len(finais),
        }

    def find_prediction_id(
        self,
        *,
        league: str,
        jogo: str,
        timestamp_ref: Optional[str] = None,
        prediction_id: Optional[str] = None,
        timestamp_tolerance_seconds: int = 60,
    ) -> Optional[str]:
        """Resolve `prediction_id` em picks_log por id direto ou tuple+proximidade de timestamp."""
        rows = self._read_rows()
        pred = str(prediction_id or "").strip()
        if pred:
            for row in rows:
                if str(row.get("prediction_id") or "").strip() == pred:
                    return pred

        home, away = self.split_match_teams(jogo)
        key = (
            str(league or "").strip().lower(),
            home.strip().lower(),
            away.strip().lower(),
        )
        candidates = []
        for row in rows:
            row_key = (
                str(row.get("league") or "").strip().lower(),
                str(row.get("team_home") or "").strip().lower(),
                str(row.get("team_away") or "").strip().lower(),
            )
            if row_key == key:
                candidates.append(row)

        if not candidates:
            return None

        ts_ref = self._parse_timestamp(str(timestamp_ref or ""))
        if ts_ref is None:
            return str(candidates[0].get("prediction_id") or "").strip() or None

        best_pid = None
        best_delta = None
        for row in candidates:
            ts_csv = self._parse_timestamp(row.get("timestamp", ""))
            if ts_csv is None:
                continue
            delta = abs((ts_ref - ts_csv).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_pid = str(row.get("prediction_id") or "").strip()

        if best_pid and best_delta is not None and best_delta <= float(timestamp_tolerance_seconds):
            return best_pid
        return None


def _resolve_data_dir() -> str:
    """Resolve diretório de dados padrão respeitando BOT_DATA_DIR."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.getenv("BOT_DATA_DIR", os.path.join(root, "data"))


def _resolve_db_path(db_arg: str) -> str:
    """Resolve caminho do DB; relativo tenta CWD e depois BOT_DATA_DIR."""
    if os.path.isabs(db_arg):
        return db_arg
    if os.path.exists(db_arg):
        return os.path.abspath(db_arg)
    return os.path.join(_resolve_data_dir(), db_arg)


def main(argv=None):
    """CLI para sincronizar outcomes do banco para o picks_log.csv."""
    parser = argparse.ArgumentParser(description="Sync outcomes de sinais -> picks_log.csv")
    parser.add_argument("--sync-db", dest="sync_db", type=str, required=True)
    parser.add_argument("--csv", dest="csv_path", type=str, default=None)
    args = parser.parse_args(argv)

    data_dir = _resolve_data_dir()
    csv_path = args.csv_path or os.path.join(data_dir, "picks_log.csv")
    db_path = _resolve_db_path(args.sync_db)

    logger = PickLogger(csv_path)
    summary = logger.sync_from_db(db_path)
    print(
        "sync complete | "
        f"finalizados={summary['total_finalizados']} "
        f"matched={summary['matched']} "
        f"updated={summary['updated']} "
        f"unmatched={summary['unmatched']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
