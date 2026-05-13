"""
P10 Strategy B: ICT Power of Three (AMD).
"""

from __future__ import annotations

from datetime import time
from typing import Any, Dict

import pandas as pd
import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

EASTERN = pytz.timezone("US/Eastern")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame index to timezone-aware Eastern index."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class ICTPowerOfThreeStrategy:
    """Identify accumulation, manipulation, and distribution phases."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def identify_accumulation(self, df: pd.DataFrame, session_data: dict) -> dict | None:
        """Detect tight consolidation accumulation zone, usually during Asia."""
        try:
            data = _normalize_df(df)
            asia = data.between_time("20:00", "00:00", inclusive="both")
            if asia.empty:
                return None

            high = float(asia["high"].max())
            low = float(asia["low"].min())
            mid = (high + low) / 2.0
            duration = len(asia)
            tr = (asia["high"] - asia["low"]).abs()
            atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())
            if atr <= 0:
                return None

            eq_hi = int((asia["high"] >= high * (1 - 0.001)).sum()) >= 2
            eq_lo = int((asia["low"] <= low * (1 + 0.001)).sum()) >= 2
            small_candles = float(tr.mean()) <= (1.1 * atr)
            if not small_candles or duration < 8:
                return None

            return {
                "range_high": high,
                "range_low": low,
                "range_midpoint": mid,
                "duration_bars": duration,
                "equal_highs_present": bool(eq_hi),
                "equal_lows_present": bool(eq_lo),
            }
        except Exception as exc:
            logger.exception("identify_accumulation failed: {}", exc)
            return None

    def identify_manipulation(self, df: pd.DataFrame, accumulation: dict) -> dict | None:
        """Detect false break beyond accumulation range followed by fast return."""
        try:
            if not accumulation:
                return None
            data = _normalize_df(df)
            high = float(accumulation["range_high"])
            low = float(accumulation["range_low"])
            width = high - low
            atr = float(((data["high"] - data["low"]).abs().rolling(14).mean().iloc[-1]))
            if atr <= 0:
                return None

            london = data.between_time("02:00", "10:30", inclusive="both")
            if london.empty:
                return None

            for i in range(0, len(london) - 4):
                row = london.iloc[i]
                ts = london.index[i].to_pydatetime()
                h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
                broke_up = h > (high + atr)
                broke_down = l < (low - atr)
                if not (broke_up or broke_down):
                    continue

                # Must return inside range in next 2-4 bars.
                window = london.iloc[i + 1 : i + 5]
                if window.empty:
                    continue
                back_inside = ((window["close"] <= high) & (window["close"] >= low)).any()
                if not back_inside:
                    continue

                fake_dir = "UP" if broke_up else "DOWN"
                expected = "DOWN" if fake_dir == "UP" else "UP"
                sweep_level = h if fake_dir == "UP" else l
                return {
                    "direction_of_fake": fake_dir,
                    "expected_distribution_direction": expected,
                    "manipulation_candle_timestamp": ts,
                    "sweep_level": float(sweep_level),
                    "confidence": 0.68,
                }
            return None
        except Exception as exc:
            logger.exception("identify_manipulation failed: {}", exc)
            return None

    def detect_distribution_entry(self, df, accumulation: dict, manipulation: dict, context: dict) -> dict | None:
        """Enter on distribution confirmation after accumulation + manipulation."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_amd.detect_distribution_entry"):
            return None
        try:
            if not accumulation or not manipulation:
                return None
            data = _normalize_df(df)
            if data.empty:
                return None

            high = float(accumulation["range_high"])
            low = float(accumulation["range_low"])
            mid = float(accumulation["range_midpoint"])
            width = high - low

            exp = manipulation["expected_distribution_direction"]
            last = data.iloc[-1]
            close = float(last["close"])

            if exp == "UP":
                # Need close back above midpoint after low sweep.
                if close <= mid:
                    return None
                entry = close
                stop = float(manipulation["sweep_level"]) - (2 * self.tick_size)
                t1 = high + width
                # std projection from manipulation leg
                leg = abs(float(manipulation["sweep_level"]) - low)
                t2 = entry + (2.0 * leg)
                t3 = entry + (4.0 * leg)
                strategy = "AMD_DISTRIBUTION_LONG"
                full_name = "ICT Power of Three — Distribution Long After Manipulation"
            else:
                if close >= mid:
                    return None
                entry = close
                stop = float(manipulation["sweep_level"]) + (2 * self.tick_size)
                t1 = low - width
                leg = abs(high - float(manipulation["sweep_level"]))
                t2 = entry - (2.0 * leg)
                t3 = entry - (4.0 * leg)
                strategy = "AMD_DISTRIBUTION_SHORT"
                full_name = "ICT Power of Three — Distribution Short After Manipulation"

            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "phase_detected": "DISTRIBUTION",
                "manipulation_direction": manipulation["direction_of_fake"],
                "expected_distribution": manipulation["expected_distribution_direction"],
                "accumulation_data": accumulation,
                "manipulation_data": manipulation,
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(t1),
                "target_2": float(t2),
                "target_3": float(t3),
                "confidence": float(round(min(1.0, 0.64 + (0.08 if accumulation.get("equal_highs_present") or accumulation.get("equal_lows_present") else 0.0)), 2)),
                "description": f"{full_name}: manipulation confirmed, distribution phase underway.",
            }
        except Exception as exc:
            logger.exception("detect_distribution_entry failed: {}", exc)
            return None
