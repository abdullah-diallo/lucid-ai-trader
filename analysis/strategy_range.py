"""
P05 Strategy A: Range Trading.
"""

from __future__ import annotations

from typing import Any, Dict, List

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
    """Normalize DataFrame index to timezone-aware Eastern datetimes."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI."""
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


class RangeTradingStrategy:
    """Identifies valid ranges and trades support/resistance rejections."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def identify_range(self, df: pd.DataFrame, min_touches: int = 2) -> dict | None:
        """Detect a valid sideways range using touch, width, and duration criteria."""
        try:
            data = _normalize_df(df)
            if len(data) < 12 or any(c not in data.columns for c in ("high", "low", "close")):
                return None

            highs = data["high"].tail(60)
            lows = data["low"].tail(60)
            resistance = float(highs.quantile(0.9))
            support = float(lows.quantile(0.1))
            midpoint = (resistance + support) / 2.0
            width = resistance - support

            tol_top = resistance * 0.002
            tol_bottom = support * 0.002
            touch_top = int(((highs >= resistance - tol_top) & (highs <= resistance + tol_top)).sum())
            touch_bottom = int(((lows >= support - tol_bottom) & (lows <= support + tol_bottom)).sum())

            in_range = ((data["high"] <= resistance + tol_top) & (data["low"] >= support - tol_bottom)).tail(60)
            bars_in_range = int(in_range.sum())

            tr = (data["high"] - data["low"]).abs()
            atr = float(tr.rolling(14).mean().iloc[-1]) if not tr.empty else 0.0
            width_ok = width >= (3.0 * max(atr, 1e-9))

            is_valid = bool(
                touch_top >= min_touches
                and touch_bottom >= min_touches
                and bars_in_range >= 8
                and width_ok
            )
            return {
                "resistance": resistance,
                "support": support,
                "midpoint": midpoint,
                "width_points": width,
                "touch_count_top": touch_top,
                "touch_count_bottom": touch_bottom,
                "bars_in_range": bars_in_range,
                "is_valid": is_valid,
            }
        except Exception as exc:
            logger.exception("identify_range failed: {}", exc)
            return None

    def detect_range_entry(self, df, range_data: dict, context: dict) -> dict | None:
        """Detect range long/short rejection entry at support or resistance."""
        try:
            if not range_data or not range_data.get("is_valid"):
                return None
            if str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper() != "RANGING":
                return None

            data = _normalize_df(df)
            if len(data) < 20:
                return None
            row = data.iloc[-1]
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            rng = max(h - l, 1e-9)
            rsi_val = float(_rsi(data["close"]).iloc[-1])
            support = float(range_data["support"])
            resistance = float(range_data["resistance"])
            midpoint = float(range_data["midpoint"])
            tol_support = support * 0.003
            tol_resistance = resistance * 0.003

            # Long at support.
            support_touch = l <= support + tol_support
            support_reject = c >= support and (min(o, c) - l) / rng >= 0.35
            if support_touch and support_reject and rsi_val < 45:
                entry = c
                stop = support - self.tick_size
                return {
                    "strategy": "RANGE_LONG",
                    "strategy_full_name": "Range Bound — Buy Support/Sell Resistance",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(midpoint),
                    "target_2": float(resistance),
                    "confidence": 0.62,
                    "description": f"Range long from support {support:.2f} with rejection candle and RSI {rsi_val:.1f}.",
                }

            # Short at resistance.
            resistance_touch = h >= resistance - tol_resistance
            resistance_reject = c <= resistance and (h - max(o, c)) / rng >= 0.35
            if resistance_touch and resistance_reject and rsi_val > 55:
                entry = c
                stop = resistance + self.tick_size
                return {
                    "strategy": "RANGE_SHORT",
                    "strategy_full_name": "Range Bound — Buy Support/Sell Resistance",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(midpoint),
                    "target_2": float(support),
                    "confidence": 0.62,
                    "description": f"Range short from resistance {resistance:.2f} with rejection candle and RSI {rsi_val:.1f}.",
                }
            return None
        except Exception as exc:
            logger.exception("detect_range_entry failed: {}", exc)
            return None
