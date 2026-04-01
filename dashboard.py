"""Dashboard textual de performance/calibracao a partir de data/picks_log.csv."""

import argparse
import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(ROOT, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

from calibrator import BucketCalibrator


BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT, "data"))
DEFAULT_PICKS_LOG = os.path.join(BOT_DATA_DIR, "picks_log.csv")

EV_THRESHOLDS = [0.02, 0.03, 0.04, 0.05, 0.06]
CONF_THRESHOLDS = [60, 64, 68, 72, 76]
EDGE_THRESHOLDS = [70, 75, 80, 85, 90]


def _to_float(value, default=0.0):
    """Converte valor para float com fallback."""
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value, default=None):
    """Converte valor para int com fallback."""
    try:
        return int(value)
    except Exception:
        return default


def load_rows(path, league=None, market=None):
    """Carrega linhas do picks_log.csv com filtros opcionais."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if league and row.get("league") != league:
                continue
            if market and row.get("market") != market:
                continue
            rows.append(row)
    return rows


def settled_rows(rows):
    """Filtra somente picks com outcome resolvido (0/1)."""
    out = []
    for row in rows:
        outcome = _to_int(row.get("outcome"), default=None)
        if outcome in (0, 1):
            out.append(row)
    return out


def _calc_pick_ev(row):
    """Calcula EV do pick a partir de prob calibrada e odd de entrada."""
    p = _to_float(row.get("calibrated_prob_model"), 0.0)
    odd = _to_float(row.get("odds_at_pick"), 0.0)
    return (p * odd) - 1.0


def _group_metrics(rows):
    """Calcula contagem, win rate, ROI e Brier por recomendacao."""
    groups = {"BET": [], "SKIP": [], "AVOID": []}
    for row in rows:
        rec = str(row.get("recomendacao_acao", "")).upper()
        if rec in groups:
            groups[rec].append(row)

    result = {}
    for rec, items in groups.items():
        n = len(items)
        if n == 0:
            result[rec] = {"n": 0, "win_rate": 0.0, "roi": 0.0, "brier": 0.0}
            continue

        wins = 0
        brier_sum = 0.0
        stake_sum = 0.0
        pnl_sum = 0.0

        for row in items:
            outcome = _to_int(row.get("outcome"), 0)
            p_cal = _to_float(row.get("calibrated_prob_model"), 0.0)
            odd = _to_float(row.get("odds_at_pick"), 0.0)
            stake = _to_float(row.get("kelly_stake"), 0.0)

            wins += outcome
            brier_sum += (p_cal - outcome) ** 2
            if stake > 0 and odd > 1.0:
                stake_sum += stake
                pnl_sum += ((odd - 1.0) * stake) if outcome == 1 else (-stake)

        win_rate = wins / n
        roi = (pnl_sum / stake_sum) if stake_sum > 0 else 0.0
        brier = brier_sum / n
        result[rec] = {"n": n, "win_rate": win_rate, "roi": roi, "brier": brier}

    return result


def _calc_clv(rows):
    """Calcula CLV medio para picks BET com closing_odds valido."""
    vals = []
    for row in rows:
        if str(row.get("recomendacao_acao", "")).upper() != "BET":
            continue
        odd_pick = _to_float(row.get("odds_at_pick"), 0.0)
        odd_close = _to_float(row.get("closing_odds"), 0.0)
        if odd_pick > 1.0 and odd_close > 1.0:
            vals.append(math.log(odd_pick / odd_close))
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def reliability_by_bucket(rows, n_buckets=10):
    """Retorna tabela de confiabilidade por bucket de probabilidade calibrada."""
    cal = BucketCalibrator(n_buckets=n_buckets, k=20)
    buckets = [{"n": 0, "pred_sum": 0.0, "out_sum": 0.0} for _ in range(n_buckets)]

    for row in rows:
        p = _to_float(row.get("calibrated_prob_model"), 0.0)
        y = _to_int(row.get("outcome"), default=None)
        if y not in (0, 1):
            continue
        idx = cal._bucket_index(p)
        buckets[idx]["n"] += 1
        buckets[idx]["pred_sum"] += p
        buckets[idx]["out_sum"] += y

    report = []
    step = 1.0 / n_buckets
    for idx, b in enumerate(buckets):
        n = b["n"]
        pred = (b["pred_sum"] / n) if n > 0 else 0.0
        emp = (b["out_sum"] / n) if n > 0 else 0.0
        gap = abs(pred - emp)
        report.append(
            {
                "bucket": f"[{idx*step:.1f},{(idx+1)*step:.1f}{']' if idx == n_buckets - 1 else ')'}",
                "n": n,
                "pred": pred,
                "emp": emp,
                "gap": gap,
                "flag": gap > 0.10,
            }
        )
    return report


def sensitivity_table(rows, thresholds, field):
    """Calcula win rate e ROI para grade de thresholds de um campo."""
    table = []
    for thr in thresholds:
        kept = []
        for row in rows:
            val = _to_float(row.get(field), 0.0)
            if val >= thr:
                kept.append(row)

        n = len(kept)
        if n == 0:
            table.append({"threshold": thr, "n": 0, "win_rate": 0.0, "roi": 0.0})
            continue

        wins = 0
        stake_sum = 0.0
        pnl_sum = 0.0
        for row in kept:
            outcome = _to_int(row.get("outcome"), 0)
            odd = _to_float(row.get("odds_at_pick"), 0.0)
            stake = _to_float(row.get("kelly_stake"), 0.0)
            wins += outcome
            if odd > 1.0 and stake > 0:
                stake_sum += stake
                pnl_sum += ((odd - 1.0) * stake) if outcome == 1 else (-stake)

        wr = wins / n
        roi = (pnl_sum / stake_sum) if stake_sum > 0 else 0.0
        table.append({"threshold": thr, "n": n, "win_rate": wr, "roi": roi})

    return table


def _print_overall(all_rows, settled):
    """Imprime resumo geral e metricas por recomendacao."""
    counts = {"BET": 0, "SKIP": 0, "AVOID": 0}
    for row in all_rows:
        rec = str(row.get("recomendacao_acao", "")).upper()
        if rec in counts:
            counts[rec] += 1

    print("Overall metrics (settled bets only)")
    print("-----------------------------------")
    print(f"Total picks: {len(all_rows)}")
    print(f"BET count:   {counts['BET']}")
    print(f"SKIP count:  {counts['SKIP']}")
    print(f"AVOID count: {counts['AVOID']}")

    metrics = _group_metrics(settled)
    print("\nBy recommendation")
    print("rec      n    win_rate      roi    brier")
    print("-----------------------------------------")
    for rec in ("BET", "SKIP", "AVOID"):
        m = metrics[rec]
        print(f"{rec:6s} {m['n']:4d}  {m['win_rate']*100:7.2f}%  {m['roi']*100:7.2f}%  {m['brier']:.4f}")

    clv = _calc_clv(settled)
    print(f"\nCLV BET (mean log(odd_pick/closing)): {clv:.6f}")


def _print_reliability(settled):
    """Imprime tabela de confiabilidade por bucket."""
    print("\nCalibration report")
    print("------------------")
    rep = reliability_by_bucket(settled, n_buckets=10)
    print("bucket          n   predicted   empirical   abs_gap   flag")
    print("-----------------------------------------------------------")
    for row in rep:
        flag = "YES" if row["flag"] else ""
        print(
            f"{row['bucket']:12s} {row['n']:4d}   {row['pred']:.4f}     {row['emp']:.4f}    {row['gap']:.4f}   {flag}"
        )


def _print_sensitivity(settled):
    """Imprime sensitivity table para EV, confiança e edge."""
    print("\nMagic numbers sensitivity")
    print("-------------------------")

    # EV e derivado da probabilidade calibrada e odd de entrada.
    settled_with_ev = []
    for row in settled:
        cloned = dict(row)
        cloned["ev"] = _calc_pick_ev(row)
        settled_with_ev.append(cloned)

    ev_table = sensitivity_table(settled_with_ev, EV_THRESHOLDS, "ev")
    conf_table = sensitivity_table(settled, CONF_THRESHOLDS, "confidence_dados")
    edge_table = sensitivity_table(settled, EDGE_THRESHOLDS, "edge_score")

    def _print_table(title, table):
        print(f"\n{title}")
        print("thr      n    win_rate      roi")
        print("-------------------------------")
        for row in table:
            print(f"{row['threshold']:>5}  {row['n']:4d}  {row['win_rate']*100:7.2f}%  {row['roi']*100:7.2f}%")

    _print_table("EV floor", ev_table)
    _print_table("Confidence floor", conf_table)
    _print_table("Edge cutoff", edge_table)


def parse_args(argv=None):
    """Parseia argumentos da CLI do dashboard."""
    parser = argparse.ArgumentParser(description="Dashboard textual do picks_log.csv")
    parser.add_argument("--min-bets", type=int, default=20)
    parser.add_argument("--league", type=str, default=None)
    parser.add_argument("--market", type=str, default=None)
    parser.add_argument("--path", type=str, default=DEFAULT_PICKS_LOG)
    return parser.parse_args(argv)


def main(argv=None):
    """Executa dashboard de performance/calibracao."""
    args = parse_args(argv)
    all_rows = load_rows(args.path, league=args.league, market=args.market)
    settled = settled_rows(all_rows)

    if len(settled) < args.min_bets:
        print(f"Settled bets insuficientes: {len(settled)} < {args.min_bets}")
        return 0

    _print_overall(all_rows, settled)
    _print_reliability(settled)
    _print_sensitivity(settled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
