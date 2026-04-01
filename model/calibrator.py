import json
from typing import Iterable


class BucketCalibrator:
    """
    Bucket calibrator com 10 buckets de largura igual no intervalo [0, 1].

    Matemática aplicada por bucket b:
      - taxa_laplace_b = (wins_b + 1) / (n_b + 2)
      - w_b = n_b / (n_b + k)
      - taxa_final_b = w_b * taxa_laplace_b + (1 - w_b) * base_rate_global

    Quando não ajustado (fit não executado), predict é identidade (pass-through).
    """

    VERSION = 1

    def __init__(self, n_buckets: int = 10, k: float = 20.0):
        if n_buckets <= 0:
            raise ValueError("n_buckets must be > 0")
        if k < 0:
            raise ValueError("k must be >= 0")

        self.n_buckets = int(n_buckets)
        self.k = float(k)
        self.is_fitted = False
        self.base_rate = 0.5
        self.buckets: list[dict] = self._default_buckets()

    def _default_buckets(self) -> list[dict]:
        step = 1.0 / self.n_buckets
        items = []
        for idx in range(self.n_buckets):
            lower = round(idx * step, 10)
            upper = round((idx + 1) * step, 10)
            items.append(
                {
                    "bucket": idx,
                    "lower": lower,
                    "upper": upper,
                    "n": 0,
                    "wins": 0,
                    "empirical_rate": 0.0,
                    "laplace_rate": 0.5,
                    "calibrated_rate": 0.5,
                    "weight": 0.0,
                }
            )
        return items

    @staticmethod
    def _clip_prob(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _bucket_index(self, raw_prob: float) -> int:
        p = self._clip_prob(raw_prob)
        idx = int(p * self.n_buckets)
        if idx >= self.n_buckets:
            idx = self.n_buckets - 1
        return idx

    def fit(self, predictions: Iterable[float], outcomes: Iterable[int]):
        preds = list(predictions)
        outs = list(outcomes)
        if len(preds) != len(outs):
            raise ValueError("predictions and outcomes must have same length")
        if not preds:
            raise ValueError("cannot fit calibrator with empty data")

        # Base rate global da amostra para shrinkage dos buckets com pouca massa.
        wins_total = 0
        for outcome in outs:
            o = int(outcome)
            if o not in (0, 1):
                raise ValueError("outcomes must be 0 or 1")
            wins_total += o
        self.base_rate = wins_total / len(outs)

        buckets = self._default_buckets()
        for raw_prob, outcome in zip(preds, outs):
            idx = self._bucket_index(raw_prob)
            buckets[idx]["n"] += 1
            buckets[idx]["wins"] += int(outcome)

        for item in buckets:
            n = item["n"]
            wins = item["wins"]

            empirical = (wins / n) if n > 0 else 0.0
            # Laplace evita extremos 0/1 em buckets pequenos.
            laplace = (wins + 1.0) / (n + 2.0)
            # Shrinkage estabiliza buckets com pouca amostra.
            w = n / (n + self.k) if (n + self.k) > 0 else 0.0
            calibrated_final = (w * laplace) + ((1.0 - w) * self.base_rate)

            item["empirical_rate"] = round(empirical, 6)
            item["laplace_rate"] = round(laplace, 6)
            item["weight"] = round(w, 6)
            item["calibrated_rate"] = round(calibrated_final, 6)

        self.buckets = buckets
        self.is_fitted = True
        return self

    def predict(self, raw_prob: float) -> float:
        p = self._clip_prob(raw_prob)
        if not self.is_fitted:
            return p
        idx = self._bucket_index(p)
        return float(self.buckets[idx]["calibrated_rate"])

    def save(self, path: str):
        payload = {
            "version": self.VERSION,
            "n_buckets": self.n_buckets,
            "k": self.k,
            "is_fitted": self.is_fitted,
            "base_rate": self.base_rate,
            "buckets": self.buckets,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        obj = cls(
            n_buckets=int(payload.get("n_buckets", 10)),
            k=float(payload.get("k", 20.0)),
        )
        obj.is_fitted = bool(payload.get("is_fitted", False))
        obj.base_rate = float(payload.get("base_rate", 0.5))
        obj.buckets = payload.get("buckets", obj._default_buckets())
        return obj
