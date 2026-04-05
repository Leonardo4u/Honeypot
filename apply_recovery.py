import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List, Set, Tuple

PICKS_PATH = Path("data/picks_log.csv")
BACKUP_PATH = Path("data/picks_log_backup_pre_recovery.csv")
AUDIT_PATH = Path("data/recovery_audit.json")


def _load_csv_rows(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_audit(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _is_team_star(row: dict) -> bool:
    home = str(row.get("team_home") or "")
    away = str(row.get("team_away") or "")
    return home.startswith("Team") or away.startswith("Team")


def _is_arsenal_chelsea(row: dict) -> bool:
    home = str(row.get("team_home") or "")
    away = str(row.get("team_away") or "")
    return "Arsenal" in home and "Chelsea" in away


def _build_sets(rows: List[dict], audit: dict) -> Tuple[Set[str], Set[str], Set[str], Dict[str, dict]]:
    orfaos = [r for r in rows if r.get("outcome") not in ("0", "1")]
    ids_orfaos = {str(r.get("prediction_id") or "") for r in orfaos}

    arsenal_rows = [r for r in rows if _is_arsenal_chelsea(r)]
    arsenal_ids = {str(r.get("prediction_id") or "") for r in arsenal_rows}
    arsenal_audit = {k: v for k, v in audit.items() if "_Arsenal_Chelsea_" in k}
    arsenal_todas_simulacoes = bool(arsenal_audit) and all(
        (v.get("confianca") == "SEM_MATCH") for v in arsenal_audit.values()
    )

    ids_team_star = {
        str(r.get("prediction_id") or "")
        for r in rows
        if _is_team_star(r)
    }

    ids_ficticios = set(ids_team_star)
    if arsenal_todas_simulacoes:
        ids_ficticios.update(arsenal_ids)

    ids_audit_medio_baixo: Set[str] = set()
    pred_to_audit: Dict[str, dict] = {}

    for _, payload in audit.items():
        conf = payload.get("confianca")
        pred_ids = [str(p) for p in payload.get("prediction_ids_afetados", [])]

        for p in pred_ids:
            pred_to_audit[p] = payload

        if conf in ("MEDIO", "BAIXO"):
            ids_audit_medio_baixo.update(pred_ids)

    ids_aplicar = (ids_audit_medio_baixo - ids_ficticios) & ids_orfaos
    ids_ficticios_orfaos = ids_ficticios & ids_orfaos
    ids_sem_match = ids_orfaos - ids_aplicar - ids_ficticios_orfaos

    return ids_aplicar, ids_ficticios_orfaos, ids_sem_match, pred_to_audit


def _backup_csv(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _derive_outcome_from_audit(row: dict, payload: dict) -> str:
    market = str(row.get("market") or "")
    outcomes = payload.get("outcomes_derivados") or {}
    return str(outcomes.get(market) or "")


def apply_recovery() -> None:
    rows = _load_csv_rows(PICKS_PATH)
    audit = _load_audit(AUDIT_PATH)

    ids_aplicar, ids_ficticios, ids_sem_match, pred_to_audit = _build_sets(rows, audit)

    _backup_csv(PICKS_PATH, BACKUP_PATH)

    updated = 0
    skipped_ficticio = 0
    skipped_sem_match = 0
    skipped_sem_outcome_derivado = 0
    updated_closing_odds = 0

    for row in rows:
        pred_id = str(row.get("prediction_id") or "")

        if pred_id in ids_ficticios:
            skipped_ficticio += 1
            continue

        if pred_id in ids_aplicar:
            payload = pred_to_audit.get(pred_id, {})
            novo_outcome = _derive_outcome_from_audit(row, payload)

            if novo_outcome in ("0", "1"):
                row["outcome"] = novo_outcome
                updated += 1

                # Mantem closing_odds como estah se nao houver no audit.
                # Caso no futuro o audit inclua esse campo, atualiza aqui.
                maybe_closing = payload.get("closing_odds")
                if maybe_closing not in (None, ""):
                    row["closing_odds"] = str(maybe_closing)
                    updated_closing_odds += 1
            else:
                skipped_sem_outcome_derivado += 1
            continue

        if pred_id in ids_sem_match:
            skipped_sem_match += 1
            continue

    fieldnames = list(rows[0].keys()) if rows else []
    with PICKS_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"backup: {BACKUP_PATH.as_posix()}")
    print(f"updated: {updated}")
    print(f"updated_closing_odds: {updated_closing_odds}")
    print(f"skipped_ficticio: {skipped_ficticio}")
    print(f"skipped_sem_match: {skipped_sem_match}")
    print(f"skipped_sem_outcome_derivado: {skipped_sem_outcome_derivado}")
    print(f"ids_aplicar: {len(ids_aplicar)}")
    print(f"ids_ficticios: {len(ids_ficticios)}")
    print(f"ids_sem_match: {len(ids_sem_match)}")


def dry_run_summary() -> None:
    rows = _load_csv_rows(PICKS_PATH)
    audit = _load_audit(AUDIT_PATH)
    ids_aplicar, ids_ficticios, ids_sem_match, _ = _build_sets(rows, audit)

    print("DRY_RUN")
    print(f"ids_aplicar: {len(ids_aplicar)}")
    print(f"ids_ficticios: {len(ids_ficticios)}")
    print(f"ids_sem_match: {len(ids_sem_match)}")


if __name__ == "__main__":
    # Execute explicitamente apenas quando a Etapa E for aprovada.
    apply_recovery()
