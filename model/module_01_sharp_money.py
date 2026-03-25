from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class OddsSnapshot:
    timestamp: datetime
    odd: float
    volume: float = 0.0
    source: str = ""


@dataclass
class MarketLine:
    match_id: str
    market: str
    selection: str
    snapshots: list[OddsSnapshot] = field(default_factory=list)

    @property
    def open_odd(self) -> Optional[float]:
        return self.snapshots[0].odd if self.snapshots else None

    @property
    def close_odd(self) -> Optional[float]:
        return self.snapshots[-1].odd if self.snapshots else None


class SharpMoneyDetector:
    def __init__(
        self,
        steam_threshold_pct: float = 0.04,
        steam_window_minutes: int = 30,
        clv_edge_threshold: float = 0.02,
        min_movement_pct: float = 0.01,
    ) -> None:
        self.steam_threshold = steam_threshold_pct
        self.steam_window = steam_window_minutes
        self.clv_threshold = clv_edge_threshold
        self.min_movement = min_movement_pct

    def closing_line_value(
        self,
        bet_odd: float,
        close_odd: float,
        overround_open: Optional[float] = None,
        overround_close: Optional[float] = None,
    ) -> float:
        overround_open = float(overround_open) if overround_open and overround_open > 0 else 1.0
        overround_close = float(overround_close) if overround_close and overround_close > 0 else 1.0
        p_bet = (1.0 / max(bet_odd, 1e-9)) / max(overround_open, 1e-9)
        p_close = (1.0 / max(close_odd, 1e-9)) / max(overround_close, 1e-9)
        return p_close - p_bet

    @staticmethod
    def estimate_overround(odds: dict[str, float]) -> float:
        valid = [float(o) for o in odds.values() if float(o) > 1.0]
        if not valid:
            return 1.0
        return max(1.0, sum(1.0 / o for o in valid))

    def line_movement_pct(self, line: MarketLine) -> float:
        if not line.open_odd or not line.close_odd:
            return 0.0
        return (line.close_odd - line.open_odd) / line.open_odd

    def detect_steam_move(self, line: MarketLine) -> list[dict]:
        events: list[dict] = []
        if len(line.snapshots) < 2:
            return events

        for i in range(1, len(line.snapshots)):
            prev = line.snapshots[i - 1]
            curr = line.snapshots[i]
            dt_minutes = (curr.timestamp - prev.timestamp).total_seconds() / 60.0
            if dt_minutes <= 0 or dt_minutes > self.steam_window:
                continue

            move = abs(curr.odd - prev.odd) / max(prev.odd, 1e-9)
            if move >= self.steam_threshold:
                events.append(
                    {
                        "timestamp": curr.timestamp.isoformat(),
                        "from_odd": prev.odd,
                        "to_odd": curr.odd,
                        "movement_pct": round(move, 4),
                        "direction": "DOWN" if curr.odd < prev.odd else "UP",
                        "severity": "HIGH" if move > self.steam_threshold * 2 else "MEDIUM",
                    }
                )
        return events

    def reverse_line_movement_signal(self, line: MarketLine, public_bet_pct: float) -> Optional[dict]:
        movement = self.line_movement_pct(line)
        is_rlm = public_bet_pct > 0.55 and movement > self.min_movement
        if not is_rlm:
            return None

        strength = min(1.0, (public_bet_pct - 0.55) / 0.45 + movement / 0.10)
        return {
            "signal": "RLM",
            "fade_side": line.selection,
            "strength": round(strength, 4),
            "confidence": "HIGH" if strength > 0.7 else "MEDIUM",
        }

    def sharp_score(
        self,
        line: MarketLine,
        our_odd: float,
        public_bet_pct: float = 0.5,
        peer_lines: Optional[list[MarketLine]] = None,
    ) -> dict:
        components: dict = {}
        score = 0.0

        if line.close_odd:
            clv = self.closing_line_value(our_odd, line.close_odd)
            components["clv"] = round(clv, 4)
            if clv >= self.clv_threshold:
                score += min(0.40, clv / 0.10 * 0.40)

        steams = self.detect_steam_move(line)
        high_steams = [s for s in steams if s["severity"] == "HIGH"]
        if high_steams:
            score += min(0.30, len(high_steams) * 0.15)
        components["steam_moves"] = len(steams)

        rlm = self.reverse_line_movement_signal(line, public_bet_pct)
        components["rlm"] = bool(rlm)
        if rlm:
            score += rlm["strength"] * 0.20

        if peer_lines:
            movements = [self.line_movement_pct(p) for p in peer_lines]
            main_move = self.line_movement_pct(line)
            same_direction = sum(
                1
                for m in movements
                if (m > 0) == (main_move > 0) and abs(m) > self.min_movement
            )
            consensus = same_direction / len(peer_lines)
            components["peer_consensus"] = round(consensus, 3)
            if consensus > 0.7:
                score += 0.10

        score = min(1.0, score)
        components["sharp_score"] = round(score, 3)
        components["recommendation"] = (
            "STRONG_SIGNAL"
            if score > 0.7
            else "MODERATE_SIGNAL"
            if score > 0.4
            else "WEAK_SIGNAL"
            if score > 0.2
            else "NO_SIGNAL"
        )
        return components


class CLVTracker:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, bet_id: str, bet_odd: float, close_odd: float, stake: float) -> None:
        detector = SharpMoneyDetector()
        clv = detector.closing_line_value(bet_odd, close_odd)
        self.records.append(
            {
                "bet_id": bet_id,
                "bet_odd": bet_odd,
                "close_odd": close_odd,
                "stake": stake,
                "clv": clv,
                "clv_roi": clv * stake,
            }
        )

    def summary(self) -> dict:
        if not self.records:
            return {}
        clvs = [r["clv"] for r in self.records]
        avg = statistics.mean(clvs)
        return {
            "n_bets": len(clvs),
            "mean_clv": round(avg, 4),
            "median_clv": round(statistics.median(clvs), 4),
            "pct_positive_clv": round(sum(1 for c in clvs if c > 0) / len(clvs), 3),
            "total_clv_roi": round(sum(r["clv_roi"] for r in self.records), 4),
            "verdict": "SHARP_BETTOR" if avg > 0.015 else "BREAK_EVEN" if avg > -0.005 else "RECREATIONAL",
        }
