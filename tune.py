"""Tuning de magic numbers via grid search em data/picks_log.csv."""

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, UTC


ROOT = os.path.dirname(os.path.abspath(__file__))
BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT, "data"))
DEFAULT_PICKS_LOG = os.path.join(BOT_DATA_DIR, "picks_log.csv")
TUNED_PATH = os.path.join(BOT_DATA_DIR, "tuned_thresholds.json")

EV_CANDIDATES = [0.02, 0.03, 0.04, 0.05, 0.06]
CONF_CANDIDATES = [60, 64, 68, 72, 76]
EDGE_CANDIDATES = [70, 75, 80, 85, 90]

CURRENT_DEFAULTS = {
    "ev_floor": 0.04,
    "confidence_floor": 64,
    "edge_cutoff": 80,
}


def _segment_key(row):
    liga = str(row.get("league") or row.get("liga") or "").strip()
    mercado = str(row.get("market") or row.get("mercado") or "").strip()
    return liga, mercado


@dataclass
class CandidateResult:
    """Resultado de um candidato de threshold."""

    threshold: float
    n: int
    win_rate: float
    roi: float
    brier: float
    score: float


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


def load_settled_rows(path):
    """Carrega somente linhas com outcome resolvido."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            outcome = _to_int(row.get("outcome"), default=None)
            if outcome in (0, 1):
                out.append(row)
    return out


def _calc_ev(row):
    """Calcula EV por pick usando probabilidade calibrada e odd de entrada."""
    p = _to_float(row.get("calibrated_prob_model"), 0.0)
    odd = _to_float(row.get("odds_at_pick"), 0.0)
    return (p * odd) - 1.0


def _score_rows(rows):
    """Calcula win_rate, ROI, Brier e score composto para um subconjunto."""
    n = len(rows)
    if n == 0:
        return CandidateResult(0, 0, 0.0, 0.0, 1.0, -1e9)

    wins = 0
    brier_sum = 0.0
    stake_sum = 0.0
    pnl_sum = 0.0

    for row in rows:
        y = _to_int(row.get("outcome"), 0)
        p = _to_float(row.get("calibrated_prob_model"), 0.0)
        odd = _to_float(row.get("odds_at_pick"), 0.0)
        stake = _to_float(row.get("kelly_stake"), 0.0)

        wins += y
        brier_sum += (p - y) ** 2
        if odd > 1.0 and stake > 0:
            stake_sum += stake
            pnl_sum += ((odd - 1.0) * stake) if y == 1 else (-stake)

    win_rate = wins / n
    roi = (pnl_sum / stake_sum) if stake_sum > 0 else 0.0
    brier = brier_sum / n
    score = (0.5 * roi) + (0.3 * win_rate) - (0.2 * brier)
    return CandidateResult(0, n, win_rate, roi, brier, score)


def evaluate_candidates(rows, candidates, extractor, min_bets):
    """Avalia grade de thresholds com restricao de n minimo."""
    evaluated = []
    for thr in candidates:
        subset = [row for row in rows if extractor(row) >= thr]
        if len(subset) < min_bets:
            continue
        res = _score_rows(subset)
        res.threshold = thr
        evaluated.append(res)
    return evaluated


def recommend_threshold(rows, name, candidates, extractor, min_bets):
    """Seleciona melhor threshold pelo score composto."""
    evaluated = evaluate_candidates(rows, candidates, extractor, min_bets)
    if not evaluated:
        return None, []
    best = max(evaluated, key=lambda x: x.score)
    return best, evaluated


def _print_results(name, current_value, best, all_results):
    """Imprime tabela de candidatos e recomendacao final."""
    print(f"\n{name}")
    print("thr      n    win_rate      roi    brier    score")
    print("--------------------------------------------------")
    for r in all_results:
        print(f"{r.threshold:>5}  {r.n:4d}  {r.win_rate*100:7.2f}%  {r.roi*100:7.2f}%  {r.brier:.4f}  {r.score:.5f}")

    if best is None:
        print(f"Recomendacao: sem candidato com n >= requisito (atual={current_value})")
        return

    current_match = None
    for r in all_results:
        if float(r.threshold) == float(current_value):
            current_match = r
            break
    improvement = (best.score - current_match.score) if current_match else 0.0
    print(
        f"Recomendado: {best.threshold} | atual: {current_value} | "
        f"improvement(score): {improvement:+.5f}"
    )


def save_tuned(path, payload):
    """Salva thresholds recomendados em JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def apply_thresholds(root_dir, thresholds):
    """Aplica thresholds recomendados em edge_score.py e analisar_jogo.py via regex."""
    edge_path = os.path.join(root_dir, "model", "edge_score.py")
    analisar_path = os.path.join(root_dir, "model", "analisar_jogo.py")

    with open(edge_path, "r", encoding="utf-8") as f:
        edge_code = f.read()
    with open(analisar_path, "r", encoding="utf-8") as f:
        analisar_code = f.read()

    edge_code = re.sub(
        r"MIN_CONFIDENCE_ACTIONABLE\s*=\s*[-+]?[0-9]*\.?[0-9]+",
        f"MIN_CONFIDENCE_ACTIONABLE = {float(thresholds['confidence_floor'])}",
        edge_code,
        count=1,
    )

    edge_code = re.sub(
        r"if\s+es\s*>=\s*[-+]?[0-9]*\.?[0-9]+\s+and\s+cf\s*>=\s*floor\s+and\s+ev_v\s*>=\s*0\.02:",
        f"if es >= {float(thresholds['edge_cutoff'])} and cf >= floor and ev_v >= 0.02:",
        edge_code,
        count=1,
    )

    analisar_code = re.sub(
        r"if\s+ev\s*<\s*[-+]?[0-9]*\.?[0-9]+:",
        f"if ev < {float(thresholds['ev_floor'])}:",
        analisar_code,
        count=1,
    )

    with open(edge_path, "w", encoding="utf-8") as f:
        f.write(edge_code)
    with open(analisar_path, "w", encoding="utf-8") as f:
        f.write(analisar_code)


def parse_args(argv=None):
    """Parseia argumentos da CLI de tuning."""
    parser = argparse.ArgumentParser(description="Tune de thresholds do bot")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--min-bets", type=int, default=20)
    parser.add_argument("--segmented", action="store_true")
    parser.add_argument("--min-segment-bets", type=int, default=40)
    parser.add_argument("--path", type=str, default=DEFAULT_PICKS_LOG)
    return parser.parse_args(argv)


def tune_segment(rows, min_bets):
    ev_best, _ = recommend_threshold(
        rows,
        "ev_floor",
        EV_CANDIDATES,
        extractor=lambda r: _calc_ev(r),
        min_bets=min_bets,
    )
    conf_best, _ = recommend_threshold(
        rows,
        "confidence_floor",
        CONF_CANDIDATES,
        extractor=lambda r: _to_float(r.get("confidence_dados"), 0.0),
        min_bets=min_bets,
    )
    edge_best, _ = recommend_threshold(
        rows,
        "edge_cutoff",
        EDGE_CANDIDATES,
        extractor=lambda r: _to_float(r.get("edge_score"), 0.0),
        min_bets=min_bets,
    )

    return {
        "ev_floor": (ev_best.threshold if ev_best else CURRENT_DEFAULTS["ev_floor"]),
        "confidence_floor": (conf_best.threshold if conf_best else CURRENT_DEFAULTS["confidence_floor"]),
        "edge_cutoff": (edge_best.threshold if edge_best else CURRENT_DEFAULTS["edge_cutoff"]),
        "n": len(rows),
    }


def persist_segment_thresholds(segments_payload):
    try:
        from data.database import upsert_segment_threshold
    except Exception:
        return 0

    applied = 0
    for item in segments_payload:
        if int(item.get("n", 0)) <= 0:
            continue
        upsert_segment_threshold(
            liga=item.get("liga") or None,
            mercado=item.get("mercado") or None,
            ev_floor=float(item["ev_floor"]),
            confidence_floor=float(item["confidence_floor"]),
            edge_cutoff=float(item["edge_cutoff"]),
            min_amostra=int(item.get("n", 0)),
            versao=str(item.get("versao", "tune_v1")),
        )
        applied += 1
    return applied


def main(argv=None):
    """Executa tuning, salva JSON e aplica thresholds opcionalmente."""
    args = parse_args(argv)
    rows = load_settled_rows(args.path)

    if not rows:
        print("Sem dados settled em picks_log.csv")
        return 0

    if args.segmented:
        buckets = {}
        for row in rows:
            liga, mercado = _segment_key(row)
            buckets.setdefault((liga, mercado), []).append(row)

        global_tuned = tune_segment(rows, min_bets=args.min_bets)
        segment_items = [
            {
                "liga": None,
                "mercado": None,
                "ev_floor": global_tuned["ev_floor"],
                "confidence_floor": global_tuned["confidence_floor"],
                "edge_cutoff": global_tuned["edge_cutoff"],
                "n": global_tuned["n"],
                "versao": "tune_v1_global",
            }
        ]

        for (liga, mercado), seg_rows in buckets.items():
            if len(seg_rows) < args.min_segment_bets:
                continue
            tuned_seg = tune_segment(seg_rows, min_bets=max(10, args.min_bets // 2))
            segment_items.append(
                {
                    "liga": liga or None,
                    "mercado": mercado or None,
                    "ev_floor": tuned_seg["ev_floor"],
                    "confidence_floor": tuned_seg["confidence_floor"],
                    "edge_cutoff": tuned_seg["edge_cutoff"],
                    "n": tuned_seg["n"],
                    "versao": "tune_v1_segment",
                }
            )

        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "segmented",
            "count": len(segment_items),
            "items": segment_items,
        }
        save_tuned(TUNED_PATH, payload)
        applied = persist_segment_thresholds(segment_items)
        print(f"Tuned segmentado salvo em: {TUNED_PATH} | segmentos aplicados no DB: {applied}")
        if args.apply:
            print("--apply ignorado em modo segmentado (runtime usa thresholds do DB)")
        return 0

    ev_best, ev_all = recommend_threshold(
        rows,
        "ev_floor",
        EV_CANDIDATES,
        extractor=lambda r: _calc_ev(r),
        min_bets=args.min_bets,
    )
    conf_best, conf_all = recommend_threshold(
        rows,
        "confidence_floor",
        CONF_CANDIDATES,
        extractor=lambda r: _to_float(r.get("confidence_dados"), 0.0),
        min_bets=args.min_bets,
    )
    edge_best, edge_all = recommend_threshold(
        rows,
        "edge_cutoff",
        EDGE_CANDIDATES,
        extractor=lambda r: _to_float(r.get("edge_score"), 0.0),
        min_bets=args.min_bets,
    )

    _print_results("EV floor", CURRENT_DEFAULTS["ev_floor"], ev_best, ev_all)
    _print_results("Confidence floor", CURRENT_DEFAULTS["confidence_floor"], conf_best, conf_all)
    _print_results("Edge cutoff", CURRENT_DEFAULTS["edge_cutoff"], edge_best, edge_all)

    tuned = {
        "ev_floor": (ev_best.threshold if ev_best else CURRENT_DEFAULTS["ev_floor"]),
        "confidence_floor": (conf_best.threshold if conf_best else CURRENT_DEFAULTS["confidence_floor"]),
        "edge_cutoff": (edge_best.threshold if edge_best else CURRENT_DEFAULTS["edge_cutoff"]),
    }
    save_tuned(TUNED_PATH, tuned)
    print(f"\nTuned thresholds salvos em: {TUNED_PATH}")

    if args.apply:
        apply_thresholds(ROOT, tuned)
        print("Thresholds aplicados em edge_score.py e analisar_jogo.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
