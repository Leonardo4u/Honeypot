import csv
import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ROOT, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

from calibrator import BucketCalibrator


BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT, "data"))


def _parse_args(argv):
    """Parseia argumentos da CLI de calibracao."""
    if len(argv) < 2:
        raise ValueError("Uso: python calibrate.py <arquivo.csv> [saida_json]")
    csv_path = argv[1]
    out_path = argv[2] if len(argv) >= 3 else os.path.join(BOT_DATA_DIR, "calibracao_prob.json")
    return csv_path, out_path


def _read_csv(path):
    """Le CSV de treino contendo prediction_id, raw_prob e outcome."""
    predictions = []
    outcomes = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"prediction_id", "raw_prob", "outcome"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV sem colunas obrigatórias: {sorted(missing)}")

        for row in reader:
            raw_prob = float(row["raw_prob"])
            outcome = int(row["outcome"])
            if outcome not in (0, 1):
                raise ValueError(f"outcome inválido para prediction_id={row.get('prediction_id')}: {outcome}")
            predictions.append(raw_prob)
            outcomes.append(outcome)
    return predictions, outcomes


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
    csv_path, out_path = _parse_args(argv)

    predictions, outcomes = _read_csv(csv_path)
    calibrator = BucketCalibrator(n_buckets=10, k=20)
    calibrator.fit(predictions, outcomes)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    calibrator.save(out_path)

    print(f"Calibrador salvo em: {out_path}")
    print(f"Amostras: {len(predictions)} | base_rate: {calibrator.base_rate:.4f}")
    _print_report(calibrator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
