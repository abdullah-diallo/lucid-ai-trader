"""
P04 Strategy A: VWAP reclaim and rejection.
"""

from __future__ import annotations

from datetime import datetime, time
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


class VWAPStrategy:
    """Detect VWAP reclaim (bull) and VWAP rejection (bear) setups."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def _is_kill_zone(self, dt: datetime) -> bool:
        """Check London/NY kill zone timing."""
        et = dt.astimezone(EASTERN) if dt.tzinfo else pytz.utc.localize(dt).astimezone(EASTERN)
        t = et.time()
        return (time(2, 0) <= t < time(5, 0)) or (time(7, 0) <= t < time(10, 0)) or (time(8, 0) <= t < time(12, 0))

    def _score_common(self, direction: str, context: dict, level: float, ts: datetime) -> tuple[float, List[str]]:
        """Apply shared confluence scoring for VWAP setups."""
        score = 0.55
        confluences: List[str] = []

        h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
        h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
        if (direction == "LONG" and h1 in {"BULLISH", "RANGING"} and h4 in {"BULLISH", "RANGING"}) or (
            direction == "SHORT" and h1 in {"BEARISH", "RANGING"} and h4 in {"BEARISH", "RANGING"}
        ):
            score += 0.10
            confluences.append("1H+4H alignment")

        has_fvg = any(
            float(f.get("bottom", level - 1)) <= level <= float(f.get("top", level + 1))
            for f in context.get("fvgs", {}).get("5m", {}).get("standard", [])
        )
        if has_fvg:
            score += 0.08
            confluences.append("FVG near VWAP")

        if self._is_kill_zone(ts):
            score += 0.08
            confluences.append("Kill zone timing")

        anchored_vwap = context.get("anchored_vwap_value")
        if anchored_vwap is not None and abs(float(anchored_vwap) - level) / max(abs(level), 1e-9) <= 0.0015:
            score += 0.07
            confluences.append("Anchored VWAP confluence")

        if bool(context.get("news_within_30m", False)):
            score -= 0.12
            confluences.append("News risk within 30m")

        if (direction == "LONG" and h4 == "BEARISH") or (direction == "SHORT" and h4 == "BULLISH"):
            score -= 0.10
            confluences.append("Strong trend risk")

        return max(0.0, min(1.0, score)), confluences

    def detect_vwap_reclaim(self, df: pd.DataFrame, context: dict) -> dict | None:
        """Detect bullish reclaim where price crosses above VWAP and holds."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_vwap.detect_vwap_reclaim"):
            return None
        try:
            data = _normalize_df(df)
            if len(data) < 6 or "close" not in data.columns:
                return None

            vwap_series = context.get("vwap_series")
            if vwap_series is None:
                vwap_value = context.get("vwap_value")
                if vwap_value is None:
                    return None
                vwap_series = pd.Series(float(vwap_value), index=data.index)
            else:
                vwap_series = pd.Series(vwap_series).reindex(data.index).ffill()

            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            if h4 == "BEARISH":
                return None

            for i in range(4, len(data) - 1):
                prior3_below = all(float(data["close"].iloc[j]) < float(vwap_series.iloc[j]) for j in range(i - 3, i))
                if not prior3_below:
                    continue

                reclaim_close = float(data["close"].iloc[i]) > float(vwap_series.iloc[i])
                hold_next = float(data["close"].iloc[i + 1]) > float(vwap_series.iloc[i + 1])
                if not (reclaim_close and hold_next):
                    continue

                # Option B: pullback entry near VWAP after reclaim.
                entry = float(data["close"].iloc[i])
                entry_ts = data.index[i].to_pydatetime()
                for k in range(i + 1, min(i + 6, len(data))):
                    low_k = float(data["low"].iloc[k]) if "low" in data.columns else float(data["close"].iloc[k])
                    vwap_k = float(vwap_series.iloc[k])
                    if abs(low_k - vwap_k) <= 0.25 and float(data["close"].iloc[k]) >= vwap_k:
                        entry = float(data["close"].iloc[k])
                        entry_ts = data.index[k].to_pydatetime()
                        break

                vwap_at_entry = float(vwap_series.loc[pd.Timestamp(entry_ts).tz_convert(EASTERN)])
                stop = vwap_at_entry - (2 * self.tick_size)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
                t1 = min([float(x["price"]) for x in swings if float(x["price"]) > entry], default=entry + 1.5 * (entry - stop))
                bsl = context.get("liquidity_pools", {}).get("5m", {}).get("bsl_levels", [])
                t2 = min([float(x["price"]) for x in bsl if float(x["price"]) > entry], default=t1)

                score, confluences = self._score_common("LONG", context, vwap_at_entry, entry_ts)
                return {
                    "strategy": "VWAP_RECLAIM_LONG",
                    "strategy_full_name": "VWAP Reclaim — Intraday Bullish Bias Confirmed",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(t1),
                    "target_2": float(t2),
                    "confidence": float(round(score, 2)),
                    "confluence_factors": confluences,
                    "description": f"VWAP reclaim held with bullish follow-through; long bias active from {vwap_at_entry:.2f}.",
                }
            return None
        except Exception as exc:
            logger.exception("detect_vwap_reclaim failed: {}", exc)
            return None

    def detect_vwap_rejection(self, df: pd.DataFrame, context: dict) -> dict | None:
        """Detect bearish rejection where price fails to reclaim VWAP from below."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_vwap.detect_vwap_rejection"):
            return None
        try:
            data = _normalize_df(df)
            if len(data) < 4 or "close" not in data.columns:
                return None

            vwap_series = context.get("vwap_series")
            if vwap_series is None:
                vwap_value = context.get("vwap_value")
                if vwap_value is None:
                    return None
                vwap_series = pd.Series(float(vwap_value), index=data.index)
            else:
                vwap_series = pd.Series(vwap_series).reindex(data.index).ffill()

            vol_avg = data["volume"].rolling(20).mean() if "volume" in data.columns else None
            for i in range(2, len(data)):
                row = data.iloc[i]
                vwap = float(vwap_series.iloc[i])
                o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
                if c >= vwap:
                    continue
                if h <= vwap:
                    continue

                rng = max(h - l, 1e-9)
                upper_wick = (h - max(o, c)) / rng
                if upper_wick <= 0.40:
                    continue

                if vol_avg is not None and not pd.isna(vol_avg.iloc[i]):
                    if float(data["volume"].iloc[i]) <= float(vol_avg.iloc[i]):
                        continue

                entry = c
                stop = h + (2 * self.tick_size)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
                t1 = max([float(x["price"]) for x in swings if float(x["price"]) < entry], default=entry - 1.5 * (stop - entry))
                ssl = context.get("liquidity_pools", {}).get("5m", {}).get("ssl_levels", [])
                t2 = max([float(x["price"]) for x in ssl if float(x["price"]) < entry], default=t1)

                ts = data.index[i].to_pydatetime()
                score, confluences = self._score_common("SHORT", context, vwap, ts)
                return {
                    "strategy": "VWAP_REJECTION_SHORT",
                    "strategy_full_name": "VWAP Rejection — Bearish Session Confirmed",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(t1),
                    "target_2": float(t2),
                    "confidence": float(round(score, 2)),
                    "confluence_factors": confluences,
                    "description": f"VWAP rejection candle failed above {vwap:.2f}; bearish continuation likely.",
                }
            return None
        except Exception as exc:
            logger.exception("detect_vwap_rejection failed: {}", exc)
            return None
