"""
P05 Strategy B: Asia session range breakout (London transition).
"""

from __future__ import annotations

from datetime import datetime, time
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
    """Normalize DataFrame index to US/Eastern timezone."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class AsiaRangeStrategy:
    """Trades Asia range breakouts during London kill zone."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def calculate_asia_range(self, df: pd.DataFrame, date: str) -> dict:
        """Calculate Asia session range from 20:00-00:00 ET for provided date."""
        try:
            data = _normalize_df(df)
            d = pd.to_datetime(date).date()
            day_data = data[data.index.date == d]
            asia = day_data.between_time("20:00", "23:59:59", inclusive="both")
            if asia.empty:
                # Include 00:00 prints immediately after midnight.
                next_day = data[data.index.date == (pd.to_datetime(date) + pd.Timedelta(days=1)).date()]
                asia = pd.concat([asia, next_day.between_time("00:00", "00:00", inclusive="both")]).sort_index()
            if asia.empty:
                raise ValueError("No Asia session bars found")

            asia_high = float(asia["high"].max())
            asia_low = float(asia["low"].min())
            asia_range = asia_high - asia_low
            asia_mid = (asia_high + asia_low) / 2.0

            # Daily ATR proxy from 1m/5m data.
            daily_ranges = data.groupby(data.index.date).apply(lambda x: float(x["high"].max() - x["low"].min()))
            daily_atr = float(daily_ranges.tail(20).mean()) if not daily_ranges.empty else max(asia_range, 1e-9)
            ratio = asia_range / max(daily_atr, 1e-9)
            if ratio < 0.30:
                quality = "TIGHT"
            elif ratio > 0.60:
                quality = "WIDE"
            else:
                quality = "NORMAL"

            return {
                "asia_high": asia_high,
                "asia_low": asia_low,
                "asia_range": asia_range,
                "asia_midpoint": asia_mid,
                "range_quality": quality,
                "date": date,
                "session": "ASIA",
            }
        except Exception as exc:
            logger.exception("calculate_asia_range failed: {}", exc)
            return {
                "asia_high": None,
                "asia_low": None,
                "asia_range": None,
                "asia_midpoint": None,
                "range_quality": "WIDE",
                "date": date,
                "session": "ASIA",
            }

    def detect_london_breakout(self, df: pd.DataFrame, asia_range: dict, context: dict) -> dict | None:
        """Detect London breakout after potential manipulation sweep of Asia range."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_asia_range.detect_london_breakout"):
            return None
        try:
            if not asia_range or asia_range.get("asia_high") is None:
                return None
            data = _normalize_df(df)
            if len(data) < 10:
                return None

            high = float(asia_range["asia_high"])
            low = float(asia_range["asia_low"])
            width = float(asia_range["asia_range"])
            tz_now = data.index[-1].to_pydatetime()
            t = tz_now.time()
            if not (time(2, 0) <= t < time(5, 0)):
                return None

            london = data.between_time("02:00", "05:00", inclusive="both")
            if london.empty:
                return None

            swept_low = bool((london["low"] < low).any())
            swept_high = bool((london["high"] > high).any())
            manipulation = swept_low or swept_high

            # Real break needs close beyond boundary by >=0.5
            bull_break_rows = london[london["close"] >= (high + 0.5)]
            bear_break_rows = london[london["close"] <= (low - 0.5)]

            direction = None
            break_row = None
            if swept_low and not bull_break_rows.empty:
                direction = "BULL"
                break_row = bull_break_rows.iloc[-1]
            elif swept_high and not bear_break_rows.empty:
                direction = "BEAR"
                break_row = bear_break_rows.iloc[-1]
            elif not bull_break_rows.empty and bear_break_rows.empty:
                direction = "BULL"
                break_row = bull_break_rows.iloc[-1]
            elif not bear_break_rows.empty and bull_break_rows.empty:
                direction = "BEAR"
                break_row = bear_break_rows.iloc[-1]

            if direction is None or break_row is None:
                return None

            # Retest entry: boundary touch after break.
            post_break = london[london.index >= break_row.name]
            entry = float(break_row["close"])
            if direction == "BULL":
                for _, r in post_break.iterrows():
                    if float(r["low"]) <= high + 0.2 and float(r["close"]) >= high:
                        entry = float(r["close"])
                        break
                stop = high - (2 * self.tick_size)
                t1 = entry + width
                t3 = entry + (2 * width)
                bsl = context.get("liquidity_pools", {}).get("1H", {}).get("bsl_levels", [])
                t2 = min([float(x["price"]) for x in bsl if float(x["price"]) > entry], default=t1)
                strategy = "ASIA_RANGE_BULL"
                full_name = "Asia Session Range Breakout — Long at London Open"
            else:
                for _, r in post_break.iterrows():
                    if float(r["high"]) >= low - 0.2 and float(r["close"]) <= low:
                        entry = float(r["close"])
                        break
                stop = low + (2 * self.tick_size)
                t1 = entry - width
                t3 = entry - (2 * width)
                ssl = context.get("liquidity_pools", {}).get("1H", {}).get("ssl_levels", [])
                t2 = max([float(x["price"]) for x in ssl if float(x["price"]) < entry], default=t1)
                strategy = "ASIA_RANGE_BEAR"
                full_name = "Asia Session Range Breakout — Short at London Open"

            confidence = 0.58
            confluences = []
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            h4_align = (direction == "BULL" and h4 == "BULLISH") or (direction == "BEAR" and h4 == "BEARISH")
            if asia_range.get("range_quality") == "TIGHT":
                confidence += 0.08
                confluences.append("Tight Asia range")
            if manipulation:
                confidence += 0.08
                confluences.append("London manipulation sweep occurred")
            if h4_align:
                confidence += 0.07
                confluences.append("4H trend agrees")
            if asia_range.get("range_quality") == "TIGHT" and manipulation and h4_align and (
                (direction == "BULL" and swept_low) or (direction == "BEAR" and swept_high)
            ):
                confidence += 0.15
                confluences.append("Highest-confidence Asia-London stack")

            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(t1),
                "target_2": float(t2),
                "target_3": float(t3),
                "confidence": float(round(min(1.0, confidence), 2)),
                "asia_range_data": asia_range,
                "manipulation_occurred": bool(manipulation),
                "description": f"{full_name}: London broke Asia range after manipulation, retest entry active.",
            }
        except Exception as exc:
            logger.exception("detect_london_breakout failed: {}", exc)
            return None
