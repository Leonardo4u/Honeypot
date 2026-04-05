import json
from dataclasses import dataclass
from typing import Iterable


class BucketCalibrator:
    """
    Bucket calibrator com 10 buckets de largura igual no intervalo [0, 1].

    Matemtica aplicada por bucket b:
      - taxa_laplace_b = (wins_b + 1) / (n_b + 2)
      - w_b = n_b / (n_b + k)
      - taxa_final_b = w_b * taxa_laplace_b + (1 - w_b) * base_rate_global

    Quando no ajustado (fit no executado), predict  identidade (pass-through).
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
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)

        obj = cls(
            n_buckets=int(payload.get("n_buckets", 10)),
            k=float(payload.get("k", 20.0)),
        )
        obj.is_fitted = bool(payload.get("is_fitted", False))
        obj.base_rate = float(payload.get("base_rate", 0.5))
        obj.buckets = payload.get("buckets", obj._default_buckets())
        return obj


@dataclass
class _CalibratorRef:
    calibrator: BucketCalibrator
    n_samples: int


class CalibratorRegistry:
    """Registry hierrquico de calibradores com fallback por liga/mercado.

    Ordem de predio:
      1) liga+mercado (quando n >= min_segment_samples)
      2) liga
      3) global

    Para baixa amostra no segmento, aplica shrinkage para o nvel superior.
    """

    VERSION = 1

    def __init__(self, global_calibrator=None, min_segment_samples: int = 100, shrinkage_k: float = 40.0):
        self.global_calibrator = global_calibrator or BucketCalibrator()
        self.min_segment_samples = int(min_segment_samples)
        self.shrinkage_k = float(shrinkage_k)
        self.by_league: dict[str, _CalibratorRef] = {}
        self.by_league_market: dict[str, _CalibratorRef] = {}

    @staticmethod
    def _mk_key(liga, mercado=None):
        liga_key = str(liga or "").strip().lower()
        if mercado is None:
            return liga_key
        return f"{liga_key}::{str(mercado or '').strip().lower()}"

    @staticmethod
    def _infer_n_samples(calibrator: BucketCalibrator) -> int:
        total = 0
        for item in calibrator.buckets:
            total += int(item.get("n", 0) or 0)
        return int(total)

    def set_global(self, calibrator: BucketCalibrator):
        self.global_calibrator = calibrator

    def set_league(self, liga, calibrator: BucketCalibrator, n_samples: int | None = None):
        key = self._mk_key(liga)
        n = self._infer_n_samples(calibrator) if n_samples is None else int(n_samples)
        self.by_league[key] = _CalibratorRef(calibrator=calibrator, n_samples=max(0, n))

    def set_league_market(self, liga, mercado, calibrator: BucketCalibrator, n_samples: int | None = None):
        key = self._mk_key(liga, mercado)
        n = self._infer_n_samples(calibrator) if n_samples is None else int(n_samples)
        self.by_league_market[key] = _CalibratorRef(calibrator=calibrator, n_samples=max(0, n))

    def _predict_ref(self, ref: _CalibratorRef | None, raw_prob: float, fallback_prob: float):
        if ref is None:
            return fallback_prob, 0

        seg_pred = float(ref.calibrator.predict(raw_prob))
        n = int(ref.n_samples or 0)
        if n <= 0:
            return fallback_prob, 0

        # shrinkage bayesiano para segmentos de baixa amostra
        w = n / (n + self.shrinkage_k)
        pred = (w * seg_pred) + ((1.0 - w) * fallback_prob)
        return float(pred), n

    def predict(self, raw_prob: float, liga=None, mercado=None):
        p_global = float(self.global_calibrator.predict(raw_prob))

        liga_ref = self.by_league.get(self._mk_key(liga))
        p_league, n_league = self._predict_ref(liga_ref, raw_prob, p_global)

        seg_ref = self.by_league_market.get(self._mk_key(liga, mercado))
        p_seg, n_seg = self._predict_ref(seg_ref, raw_prob, p_league)

        if n_seg >= self.min_segment_samples:
            return p_seg
        if n_league > 0:
            return p_league
        return p_global

    @staticmethod
    def _serialize_ref(ref: _CalibratorRef):
        return {
            "n_samples": int(ref.n_samples),
            "calibrator": {
                "version": BucketCalibrator.VERSION,
                "n_buckets": ref.calibrator.n_buckets,
                "k": ref.calibrator.k,
                "is_fitted": ref.calibrator.is_fitted,
                "base_rate": ref.calibrator.base_rate,
                "buckets": ref.calibrator.buckets,
            },
        }

    @staticmethod
    def _deserialize_calibrator(payload: dict):
        cal = BucketCalibrator(
            n_buckets=int(payload.get("n_buckets", 10)),
            k=float(payload.get("k", 20.0)),
        )
        cal.is_fitted = bool(payload.get("is_fitted", False))
        cal.base_rate = float(payload.get("base_rate", 0.5))
        cal.buckets = payload.get("buckets", cal._default_buckets())
        return cal

    def save(self, path: str):
        payload = {
            "registry_version": self.VERSION,
            "min_segment_samples": self.min_segment_samples,
            "shrinkage_k": self.shrinkage_k,
            "global": {
                "version": BucketCalibrator.VERSION,
                "n_buckets": self.global_calibrator.n_buckets,
                "k": self.global_calibrator.k,
                "is_fitted": self.global_calibrator.is_fitted,
                "base_rate": self.global_calibrator.base_rate,
                "buckets": self.global_calibrator.buckets,
            },
            "by_league": {
                key: self._serialize_ref(ref)
                for key, ref in self.by_league.items()
            },
            "by_league_market": {
                key: self._serialize_ref(ref)
                for key, ref in self.by_league_market.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)

        # backward compatibility: arquivo legado de BucketCalibrator
        if "registry_version" not in payload:
            legacy = cls()
            legacy.set_global(cls._deserialize_calibrator(payload))
            return legacy

        reg = cls(
            global_calibrator=cls._deserialize_calibrator(payload.get("global", {})),
            min_segment_samples=int(payload.get("min_segment_samples", 100)),
            shrinkage_k=float(payload.get("shrinkage_k", 40.0)),
        )

        for key, raw in (payload.get("by_league") or {}).items():
            c_payload = raw.get("calibrator", {}) if isinstance(raw, dict) else {}
            ref = _CalibratorRef(
                calibrator=cls._deserialize_calibrator(c_payload),
                n_samples=int((raw or {}).get("n_samples", 0)),
            )
            reg.by_league[str(key)] = ref

        for key, raw in (payload.get("by_league_market") or {}).items():
            c_payload = raw.get("calibrator", {}) if isinstance(raw, dict) else {}
            ref = _CalibratorRef(
                calibrator=cls._deserialize_calibrator(c_payload),
                n_samples=int((raw or {}).get("n_samples", 0)),
            )
            reg.by_league_market[str(key)] = ref

        return reg
