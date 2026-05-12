"""
P06 Strategy B: Gap and Go.
"""

from __future__ import annotations

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
    """Normalize DataFrame index to timezone-aware Eastern datetimes."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class GapAndGoStrategy:
    """Detect and trade catalyst-backed opening gap continuation."""

    def detect_gap(self, current_open: float, prev_close: float, instrument: str) -> dict | None:
        """Detect significant opening gap based on futures thresholds."""
        try:
            current_open = float(current_open)
            prev_close = float(prev_close)
            gap_size = current_open - prev_close
            gap_percent = abs(gap_size) / max(abs(prev_close), 1e-9) * 100.0
            direction = "UP" if gap_size > 0 else "DOWN"
            inst = instrument.upper()
            min_gap = 5.0 if inst == "MES" else 20.0 if inst == "MNQ" else 5.0
            is_significant = abs(gap_size) >= min_gap
            return {
                "gap_size": float(gap_size),
                "gap_percent": float(gap_percent),
                "direction": direction,
                "is_significant": bool(is_significant),
                "prev_close": prev_close,
                "current_open": current_open,
            }
        except Exception as exc:
            logger.exception("detect_gap failed: {}", exc)
            return None

    def detect_gap_and_go(self, df: pd.DataFrame, gap: dict, news_data: dict, context: dict) -> dict | None:
        """Detect first-minute confirmed gap continuation with VWAP and catalyst checks."""
        try:
            if not gap or not gap.get("is_significant"):
                return None
            has_catalyst = bool(news_data and (news_data.get("event") or news_data.get("can_trade") or news_data.get("impact") == "HIGH"))
            if not has_catalyst:
                return None

            data = _normalize_df(df)
            if len(data) < 2 or any(c not in data.columns for c in ("open", "high", "low", "close")):
                return None

            first = data.iloc[0]
            direction = gap["direction"]
            first_up = float(first["close"]) > float(first["open"])
            first_down = float(first["close"]) < float(first["open"])
            if direction == "UP" and not first_up:
                return None
            if direction == "DOWN" and not first_down:
                return None

            vwap_val = context.get("vwap_value")
            if vwap_val is None:
                return None
            vwap_val = float(vwap_val)
            at_931 = data.iloc[min(1, len(data) - 1)]
            px_931 = float(at_931["close"])
            if direction == "UP" and px_931 <= vwap_val:
                return None
            if direction == "DOWN" and px_931 >= vwap_val:
                return None

            entry = float(first["high"]) + 0.01 if direction == "UP" else float(first["low"]) - 0.01
            # Optional pullback entry to pre-market high/low.
            pm_high = context.get("premarket_high")
            pm_low = context.get("premarket_low")
            if direction == "UP" and pm_high is not None and abs(float(pm_high) - px_931) / max(abs(px_931), 1e-9) <= 0.002:
                entry = float(pm_high)
            if direction == "DOWN" and pm_low is not None and abs(float(pm_low) - px_931) / max(abs(px_931), 1e-9) <= 0.002:
                entry = float(pm_low)

            stop = float(first["low"]) if direction == "UP" else float(first["high"])
            gap_size = float(abs(gap["gap_size"]))
            open_px = float(gap["current_open"])
            prev_day_high = context.get("prev_day_high")
            prev_day_low = context.get("prev_day_low")

            if direction == "UP":
                t1 = open_px + gap_size
                t2 = (float(prev_day_high) + gap_size) if prev_day_high is not None else t1
                t3 = open_px + (2.0 * gap_size)
                strategy = "GAP_GO_LONG"
                full_name = "Gap and Go — Catalyst-Backed Continuation Long"
                gap_fill_risk = float(first["close"]) < open_px
            else:
                t1 = open_px - gap_size
                t2 = (float(prev_day_low) - gap_size) if prev_day_low is not None else t1
                t3 = open_px - (2.0 * gap_size)
                strategy = "GAP_GO_SHORT"
                full_name = "Gap and Go — Catalyst-Backed Continuation Short"
                gap_fill_risk = float(first["close"]) > open_px

            confidence = 0.62 - (0.20 if gap_fill_risk else 0.0)
            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(t1),
                "target_2": float(t2),
                "target_3": float(t3),
                "gap_data": gap,
                "has_catalyst": bool(has_catalyst),
                "gap_fill_risk": bool(gap_fill_risk),
                "confidence": float(round(max(0.0, min(1.0, confidence)), 2)),
                "description": f"{full_name}: significant {'gap up' if direction=='UP' else 'gap down'} with catalyst and first-minute continuation.",
            }
        except Exception as exc:
            logger.exception("detect_gap_and_go failed: {}", exc)
            return None
