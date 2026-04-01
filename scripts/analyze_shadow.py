"""Analisa logs da policy v2 em shadow mode e produz veredito de promocao."""

import argparse
import csv
import json
import math
import os
from collections import Counter, defaultdict


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT_DATA_DIR = os.getenv("BOT_DATA_DIR", os.path.join(ROOT_DIR, "data"))
if os.path.basename(os.path.normpath(BOT_DATA_DIR)).lower() == "data":
    LOGS_DIR = os.path.join(os.path.dirname(os.path.normpath(BOT_DATA_DIR)), "logs")
else:
    LOGS_DIR = os.path.join(BOT_DATA_DIR, "logs")

SHADOW_LOG_PATH = os.path.join(LOGS_DIR, "policy_v2_shadow.log")
PICKS_LOG_PATH = os.path.join(BOT_DATA_DIR, "picks_log.csv")


def _to_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def _read_jsonl(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def _read_picks(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _calc_clv_from_row(row):
    odd_pick = _to_float(row.get("odds_at_pick"), default=None)
    odd_close = _to_float(row.get("closing_odds"), default=None)
    outcome = row.get("outcome", "").strip()
    if outcome not in ("0", "1"):
        return None
    if odd_pick is None or odd_close is None or odd_pick <= 1.0 or odd_close <= 1.0:
        return None
    return math.log(odd_pick / odd_close)


def build_report(min_picks=20, shadow_log_path=SHADOW_LOG_PATH, picks_log_path=PICKS_LOG_PATH):
    """Gera relatório e veredito PROMOTE/WAIT/DO NOT PROMOTE para policy v2."""
    blocked_events = _read_jsonl(shadow_log_path)
    picks_rows = _read_picks(picks_log_path)

    blocked_ids = {
        str(evt.get("prediction_id", "")).strip()
        for evt in blocked_events
        if str(evt.get("prediction_id", "")).strip()
    }

    picks_by_id = {}
    for row in picks_rows:
        pid = str(row.get("prediction_id", "")).strip()
        if pid:
            picks_by_id[pid] = row

    # Total analisado aproximado: sinais bloqueados + sinais registrados em picks_log.
    analyzed_ids = set(picks_by_id.keys()) | blocked_ids
    total_analyzed = len(analyzed_ids)
    total_blocked = len(blocked_ids)
    rejection_rate = (total_blocked / total_analyzed * 100.0) if total_analyzed > 0 else 0.0

    # Rejeicao por liga/mercado: bloqueados / analisados no grupo.
    analyzed_by_league = defaultdict(int)
    analyzed_by_market = defaultdict(int)
    for row in picks_rows:
        analyzed_by_league[str(row.get("league", ""))] += 1
        analyzed_by_market[str(row.get("market", ""))] += 1
    for evt in blocked_events:
        analyzed_by_league[str(evt.get("league", ""))] += 1
        analyzed_by_market[str(evt.get("market", ""))] += 1

    blocked_by_league = Counter(str(evt.get("league", "")) for evt in blocked_events)
    blocked_by_market = Counter(str(evt.get("market", "")) for evt in blocked_events)

    reject_rate_by_league = {}
    for league, blocked_count in blocked_by_league.items():
        base = analyzed_by_league.get(league, 0)
        reject_rate_by_league[league] = (blocked_count / base * 100.0) if base > 0 else 0.0

    reject_rate_by_market = {}
    for market, blocked_count in blocked_by_market.items():
        base = analyzed_by_market.get(market, 0)
        reject_rate_by_market[market] = (blocked_count / base * 100.0) if base > 0 else 0.0

    top_reasons = Counter(str(evt.get("reject_reason", "unknown")) for evt in blocked_events).most_common(3)

    blocked_clvs = []
    passed_clvs = []
    for pid, row in picks_by_id.items():
        clv = _calc_clv_from_row(row)
        if clv is None:
            continue
        if pid in blocked_ids:
            blocked_clvs.append(clv)
        else:
            passed_clvs.append(clv)

    mean_blocked_clv = (sum(blocked_clvs) / len(blocked_clvs)) if blocked_clvs else None
    mean_passed_clv = (sum(passed_clvs) / len(passed_clvs)) if passed_clvs else None

    settled_picks_for_clv = len(blocked_clvs) + len(passed_clvs)
    enough_picks = settled_picks_for_clv >= int(min_picks)
    healthy_reject_rate = 5.0 <= rejection_rate <= 35.0

    if not enough_picks:
        verdict = "WAIT"
    elif mean_blocked_clv is not None and mean_blocked_clv > 0:
        verdict = "DO NOT PROMOTE"
    elif healthy_reject_rate and (mean_blocked_clv is None or mean_blocked_clv <= 0):
        verdict = "PROMOTE"
    else:
        verdict = "WAIT"

    return {
        "total_analyzed": total_analyzed,
        "total_would_have_blocked": total_blocked,
        "rejection_rate_pct": rejection_rate,
        "reject_rate_by_league_pct": dict(sorted(reject_rate_by_league.items())),
        "reject_rate_by_market_pct": dict(sorted(reject_rate_by_market.items())),
        "top_reject_reasons": top_reasons,
        "mean_clv_blocked": mean_blocked_clv,
        "mean_clv_passed": mean_passed_clv,
        "settled_picks_for_clv": settled_picks_for_clv,
        "min_picks_required": int(min_picks),
        "verdict": verdict,
    }


def _fmt_clv(value):
    if value is None:
        return "n/a"
    return f"{value:+.6f}"


def main(argv=None):
    """CLI principal de análise de shadow mode da policy v2."""
    parser = argparse.ArgumentParser(description="Analisa shadow log da policy v2")
    parser.add_argument("--min-picks", type=int, default=20)
    args = parser.parse_args(argv)

    report = build_report(min_picks=args.min_picks)

    print("Shadow mode analysis (policy_v2)")
    print("--------------------------------")
    print(f"Total signals analyzed: {report['total_analyzed']}")
    print(f"Total would-have-been-blocked: {report['total_would_have_blocked']}")
    print(f"Rejection rate: {report['rejection_rate_pct']:.2f}%")

    print("\nRejection rate by league")
    for league, rate in report["reject_rate_by_league_pct"].items():
        print(f"- {league}: {rate:.2f}%")

    print("\nRejection rate by market")
    for market, rate in report["reject_rate_by_market_pct"].items():
        print(f"- {market}: {rate:.2f}%")

    print("\nTop reject reasons")
    for reason, count in report["top_reject_reasons"]:
        print(f"- {reason}: {count}")

    print("\nCLV comparison")
    print(f"- blocked mean CLV: {_fmt_clv(report['mean_clv_blocked'])}")
    print(f"- passed mean CLV:  {_fmt_clv(report['mean_clv_passed'])}")
    print(
        f"- settled picks used: {report['settled_picks_for_clv']} "
        f"(min required: {report['min_picks_required']})"
    )

    print(f"\nPromotion verdict: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
