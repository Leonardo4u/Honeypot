from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List


@dataclass
class FoldResult:
    fold_id: str
    data_inicio: str
    data_fim: str
    brier_val: float
    brier_test: float
    roi_test: float
    n_picks: int


class WalkForwardValidator:
    def __init__(self, train_months=12, val_months=3, test_months=3):
        self.train_months = int(train_months)
        self.val_months = int(val_months)
        self.test_months = int(test_months)

    @staticmethod
    def _to_dt(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    return datetime.strptime(value[: len(fmt)], fmt)
                except Exception:
                    continue
        return None

    @staticmethod
    def _month_key(dt: datetime):
        return dt.year * 12 + dt.month

    @staticmethod
    def _calc_brier(rows):
        vals = []
        for r in rows:
            p = float(r.get("prob") or 0.0)
            y = int(r.get("outcome") or 0)
            vals.append((p - y) ** 2)
        if not vals:
            return 0.0
        return float(sum(vals) / len(vals))

    @staticmethod
    def _calc_roi(rows):
        stake_sum = 0.0
        pnl_sum = 0.0
        for r in rows:
            y = int(r.get("outcome") or 0)
            odd = float(r.get("odd") or 0.0)
            stake = float(r.get("stake") or 1.0)
            if odd <= 1.0 or stake <= 0:
                continue
            stake_sum += stake
            pnl_sum += ((odd - 1.0) * stake) if y == 1 else (-stake)
        if stake_sum <= 0:
            return 0.0
        return float(pnl_sum / stake_sum)

    def run_folds(
        self,
        rows: Iterable[dict],
        fit_fn: Callable[[List[dict]], None],
        select_fn: Callable[[List[dict]], dict],
        apply_fn: Callable[[dict, List[dict]], List[dict]],
    ):
        data = []
        for r in rows:
            dt = self._to_dt(r.get("date"))
            if dt is None:
                continue
            r2 = dict(r)
            r2["_dt"] = dt
            data.append(r2)

        data.sort(key=lambda x: x["_dt"])
        if not data:
            return []

        months = sorted({self._month_key(r["_dt"]) for r in data})
        results: List[FoldResult] = []

        cursor = 0
        while cursor < len(months):
            train_start_i = cursor
            train_end_i = train_start_i + self.train_months
            val_end_i = train_end_i + self.val_months
            test_end_i = val_end_i + self.test_months

            if test_end_i > len(months):
                break

            train_months = set(months[train_start_i:train_end_i])
            val_months = set(months[train_end_i:val_end_i])
            test_months = set(months[val_end_i:test_end_i])

            train_rows = [r for r in data if self._month_key(r["_dt"]) in train_months]
            val_rows = [r for r in data if self._month_key(r["_dt"]) in val_months]
            test_rows = [r for r in data if self._month_key(r["_dt"]) in test_months]

            if not train_rows or not val_rows or not test_rows:
                cursor += 1
                continue

            fit_fn(train_rows)
            params = select_fn(val_rows)
            predicted_test = apply_fn(params, test_rows)

            brier_val = self._calc_brier(val_rows)
            brier_test = self._calc_brier(predicted_test)
            roi_test = self._calc_roi(predicted_test)

            fold_id = f"fold_{len(results)+1:02d}"
            results.append(
                FoldResult(
                    fold_id=fold_id,
                    data_inicio=min(r["_dt"] for r in test_rows).date().isoformat(),
                    data_fim=max(r["_dt"] for r in test_rows).date().isoformat(),
                    brier_val=round(float(brier_val), 6),
                    brier_test=round(float(brier_test), 6),
                    roi_test=round(float(roi_test), 6),
                    n_picks=len(predicted_test),
                )
            )
            cursor += self.test_months

        return results
