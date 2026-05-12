"""
P06 Strategy A: Post-news spike continuation.
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
    """Normalize DataFrame index to US/Eastern timezone."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class NewsSpikeContinuationStrategy:
    """Trades continuation after high-impact news spike settles."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def detect_post_news_entry(self, df: pd.DataFrame, news_spike: dict, context: dict) -> dict | None:
        """Detect post-news mini-range breakout continuation 3+ minutes after event."""
        try:
            if not news_spike or not news_spike.get("can_trade"):
                return None
            if int(news_spike.get("minutes_since_news", 0)) < 3:
                return None

            data = _normalize_df(df)
            if len(data) < 8 or any(c not in data.columns for c in ("open", "high", "low", "close")):
                return None

            direction = str(news_spike.get("direction", "NEUTRAL")).upper()
            if direction not in {"BULLISH", "BEARISH"}:
                return None

            vwap_bias = str(context.get("vwap_position", {}).get("bias", "NEUTRAL")).upper()
            if (direction == "BULLISH" and vwap_bias == "BEARISH") or (direction == "BEARISH" and vwap_bias == "BULLISH"):
                return None

            # Post-news 2-5 bar consolidation.
            cons = data.tail(5)
            cons_high = float(cons["high"].max())
            cons_low = float(cons["low"].min())
            cons_range = cons_high - cons_low
            last = data.iloc[-1]
            close = float(last["close"])

            if direction == "BULLISH":
                trigger = close > cons_high
                if not trigger:
                    return None
                entry = close
                stop = cons_low
                t1 = entry + cons_range
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
                t2 = min([float(x["price"]) for x in swings if float(x["price"]) > entry], default=t1)
                day_high = context.get("session_levels", {}).get("NY", {}).get("session_high")
                t3 = float(day_high) if day_high and float(day_high) > entry else t2
                strategy = "NEWS_CONTINUATION_LONG"
                full_name = "Post-News Continuation — Long after Confirmed Direction"
            else:
                trigger = close < cons_low
                if not trigger:
                    return None
                entry = close
                stop = cons_high
                t1 = entry - cons_range
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
                t2 = max([float(x["price"]) for x in swings if float(x["price"]) < entry], default=t1)
                day_low = context.get("session_levels", {}).get("NY", {}).get("session_low")
                t3 = float(day_low) if day_low and float(day_low) < entry else t2
                strategy = "NEWS_CONTINUATION_SHORT"
                full_name = "Post-News Continuation — Short after Confirmed Direction"

            # Spike-created FVG confluence.
            fvg_bonus = any(int(f.get("age_bars", 999)) <= 5 for f in context.get("fvgs", {}).get("1m", {}).get("standard", []))
            confidence = 0.60 + (0.07 if fvg_bonus else 0.0)
            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "news_event": news_spike.get("event"),
                "minutes_since_news": int(news_spike.get("minutes_since_news", 0)),
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(t1),
                "target_2": float(t2),
                "target_3": float(t3),
                "confidence": float(round(min(1.0, confidence), 2)),
                "description": f"{full_name}: break of post-news consolidation after {news_spike.get('event')}.",
            }
        except Exception as exc:
            logger.exception("detect_post_news_entry failed: {}", exc)
            return None
