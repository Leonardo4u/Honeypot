import csv
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
from model.calibrator import BucketCalibrator, CalibratorRegistry


BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT, "data"))


def _parse_args(argv):
    """Parseia argumentos da CLI de calibracao."""
    parser = argparse.ArgumentParser(description="Fit de calibrador de probabilidades")
    parser.add_argument("csv_path", type=str, help="CSV com prediction_id, raw_prob, outcome")
    parser.add_argument(
        "out_path",
        nargs="?",
        default=os.path.join(BOT_DATA_DIR, "calibracao_prob.json"),
        help="Arquivo de sada JSON",
    )
    parser.add_argument("--segmented", action="store_true", help="Gera registry segmentado por liga e mercado")
    parser.add_argument("--min-segment-samples", type=int, default=100)
    parser.add_argument("--segment-fit-min", type=int, default=40)
    return parser.parse_args(argv[1:])


def _read_csv(path):
    """Le CSV de treino contendo prediction_id, raw_prob e outcome."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"prediction_id", "raw_prob_model", "outcome"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV sem colunas obrigatórias: {sorted(missing)}")

        for row in reader:
            raw_prob = float(row["raw_prob_model"])
            outcome_raw = (row.get("outcome") or "").strip()
            if outcome_raw not in ("0", "1"):
                continue
            outcome = int(outcome_raw)
            rows.append(
                {
                    "prediction_id": row.get("prediction_id", ""),
                    "raw_prob_model": raw_prob,
                    "outcome": outcome,
                    "league": (row.get("league") or row.get("liga") or "").strip(),
                    "market": (row.get("market") or row.get("mercado") or "").strip(),
                }
            )
    return rows


def _print_report(cal):
    """Imprime tabela simples de confiabilidade por bucket."""
    print("\nReliability report")
    print("bucket    n   empirical_rate   calibrated_rate")
    print("----------------------------------------------")
    for b in cal.buckets:
        faixa = f"[{b['lower']:.1f},{b['upper']:.1f})"
        if b["bucket"] == (cal.n_buckets - 1):
            faixa = f"[{b['lower']:.1f},1.0]"
        print(
            f"{faixa:11s} {b['n']:3d} "
            f"{b['empirical_rate']:14.4f} {b['calibrated_rate']:16.4f}"
        )



def main(argv=None):
    """Executa rotina de fit do calibrador e persistencia JSON."""
    argv = argv or sys.argv
    args = _parse_args(argv)

    rows = _read_csv(args.csv_path)
    predictions = [r["raw_prob_model"] for r in rows]
    outcomes = [r["outcome"] for r in rows]
    calibrator = BucketCalibrator(n_buckets=10, k=20).fit(predictions, outcomes)

    os.makedirs(os.path.dirname(args.out_path), exist_ok=True)
    if not args.segmented:
        calibrator.save(args.out_path)
    else:
        reg = CalibratorRegistry(
            global_calibrator=calibrator,
            min_segment_samples=max(1, int(args.min_segment_samples)),
        )

        by_league = {}
        by_league_market = {}
        for row in rows:
            liga = row["league"]
            mercado = row["market"]
            if liga:
                by_league.setdefault(liga, []).append(row)
            if liga and mercado:
                by_league_market.setdefault((liga, mercado), []).append(row)

        for liga, grp in by_league.items():
            if len(grp) < max(1, int(args.segment_fit_min)):
                continue
            cal = BucketCalibrator(n_buckets=10, k=20).fit(
                [g["raw_prob_model"] for g in grp],
                [g["outcome"] for g in grp],
            )
            reg.set_league(liga, cal, n_samples=len(grp))

        for (liga, mercado), grp in by_league_market.items():
            if len(grp) < max(1, int(args.segment_fit_min)):
                continue
            cal = BucketCalibrator(n_buckets=10, k=20).fit(
                [g["raw_prob_model"] for g in grp],
                [g["outcome"] for g in grp],
            )
            reg.set_league_market(liga, mercado, cal, n_samples=len(grp))

        reg.save(args.out_path)

    print(f"Calibrador salvo em: {args.out_path}")
    print(f"Amostras: {len(predictions)} | base_rate: {calibrator.base_rate:.4f}")
    if args.segmented:
        print(
            "Segmentado: "
            f"ligas={len(getattr(reg, 'by_league', {}))} "
            f"liga+mercado={len(getattr(reg, 'by_league_market', {}))}"
        )
    _print_report(calibrator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
