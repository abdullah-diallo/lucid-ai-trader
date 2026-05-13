"""
News sentiment and high-impact event utilities.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
    """Normalize DataFrame index to timezone-aware US/Eastern."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _to_eastern(dt: datetime) -> datetime:
    """Normalize datetime to US/Eastern timezone."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(EASTERN)


class NewsSentimentEngine:
    """News helper methods including spike setup detection."""

    HIGH_IMPACT_EVENTS = [
        "FOMC Rate Decision",
        "Non-Farm Payrolls",
        "CPI (Inflation)",
        "PPI",
        "GDP",
        "Retail Sales",
        "JOLTS Job Openings",
        "Fed Chair Speech",
    ]

    def detect_news_spike_setup(self, df: pd.DataFrame, news_events: list) -> dict | None:
        """Detect post-news spike setup and direction after initial spike settles."""
        try:
            if df is None or df.empty or not news_events:
                return None
            data = _normalize_df(df)
            for c in ("open", "high", "low", "close"):
                if c not in data.columns:
                    return None
            if len(data) < 10:
                return None

            now_et = data.index.max().to_pydatetime()
            high_impact = []
            for ev in news_events:
                name = str(ev.get("name", ""))
                if any(x.lower() in name.lower() for x in self.HIGH_IMPACT_EVENTS):
                    ev_time = ev.get("timestamp")
                    if ev_time is None:
                        continue
                    ev_dt = _to_eastern(pd.Timestamp(ev_time).to_pydatetime())
                    high_impact.append({"name": name, "timestamp": ev_dt, "sentiment": ev.get("sentiment", "NEUTRAL")})
            if not high_impact:
                return None

            latest = sorted(high_impact, key=lambda x: x["timestamp"])[-1]
            ev_dt = latest["timestamp"]
            minutes_since = int((now_et - ev_dt).total_seconds() // 60)

            # Blackout windows: 30m before and 2m after event.
            if -30 <= minutes_since <= 2:
                return {
                    "event": latest["name"],
                    "event_time": ev_dt,
                    "is_blackout": True,
                    "can_trade": False,
                    "blackout_reason": "Within pre/post high-impact news blackout window.",
                }

            if minutes_since < 3:
                return None

            post = data[data.index >= ev_dt]
            if len(post) < 4:
                return None

            tr = (data["high"] - data["low"]).abs()
            atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())
            spike_window = post.iloc[:3]
            spike_move = float(spike_window["high"].max() - spike_window["low"].min())
            if spike_move < (2.0 * max(atr, 1e-9)):
                return None

            # Initial 1-2 minute direction by close, not wick.
            first_close = float(post["close"].iloc[0])
            second_close = float(post["close"].iloc[min(1, len(post) - 1)])
            direction = "BULLISH" if second_close >= first_close else "BEARISH"

            # Settled condition: either consolidation (small range) or partial reversal.
            settle = post.iloc[2:6] if len(post) >= 6 else post.iloc[2:]
            if settle.empty:
                return None
            settle_range = float(settle["high"].max() - settle["low"].min())
            consolidating = settle_range <= (1.2 * max(atr, 1e-9))
            spike_high = float(spike_window["high"].max())
            spike_low = float(spike_window["low"].min())
            reversed_some = (
                (direction == "BULLISH" and float(settle["low"].min()) < spike_high - (0.35 * spike_move))
                or (direction == "BEARISH" and float(settle["high"].max()) > spike_low + (0.35 * spike_move))
            )
            if not (consolidating or reversed_some):
                return None

            return {
                "event": latest["name"],
                "event_time": ev_dt,
                "minutes_since_news": minutes_since,
                "spike_size_points": spike_move,
                "atr": atr,
                "spike_multiple_atr": spike_move / max(atr, 1e-9),
                "direction": direction,
                "is_blackout": False,
                "can_trade": minutes_since >= 3,
                "description": f"Post-news setup detected after {latest['name']}; spike settled and direction appears {direction}.",
            }
        except Exception as exc:
            logger.exception("detect_news_spike_setup failed: %s", exc)
            return None
