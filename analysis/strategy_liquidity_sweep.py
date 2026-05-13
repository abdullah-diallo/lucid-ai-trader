"""
P02 Strategy A: Liquidity Sweep Reversal.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List

import pandas as pd
import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from analysis.trading_concepts import LiquidityAnalyzer

EASTERN = pytz.timezone("US/Eastern")


def _to_eastern_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame index to US/Eastern timezone."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class LiquiditySweepStrategy:
    """Detects stop-hunt sweeps and reversal entries."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size
        self.la = LiquidityAnalyzer()

    def _is_kill_zone(self, dt: datetime) -> bool:
        """Return True during London/NY kill zones."""
        et = dt.astimezone(EASTERN) if dt.tzinfo else pytz.utc.localize(dt).astimezone(EASTERN)
        t = et.time()
        return (time(2, 0) <= t < time(5, 0)) or (time(7, 0) <= t < time(10, 0)) or (time(8, 0) <= t < time(12, 0))

    def _at_ob_or_fvg(self, level: float, context: dict, timeframe: str) -> bool:
        """Check if level overlaps OB/FVG area on timeframe."""
        for ob in context.get("order_blocks", {}).get(timeframe, {}).get("standard", []):
            if float(ob.get("low", level - 1)) <= level <= float(ob.get("high", level + 1)):
                return True
        for fvg in context.get("fvgs", {}).get(timeframe, {}).get("standard", []):
            if float(fvg.get("bottom", level - 1)) <= level <= float(fvg.get("top", level + 1)):
                return True
        return False

    def detect_sweep_reversal(self, df: pd.DataFrame, context: dict, timeframe: str) -> list:
        """Detect sweep confirmations and generate reversal entries."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_liquidity_sweep.detect_sweep_reversal"):
            return []
        try:
            data = _to_eastern_df(df)
            for c in ("open", "high", "low", "close"):
                if c not in data.columns:
                    return []
            if len(data) < 4:
                return []

            swings = context.get("market_structure", {}).get(timeframe, {}).get("swings", {"swing_highs": [], "swing_lows": []})
            pools = self.la.detect_liquidity_pools(data, swings)
            bsl_levels = [float(x["price"]) for x in pools.get("bsl_levels", [])]
            ssl_levels = [float(x["price"]) for x in pools.get("ssl_levels", [])]
            equal_high_prices = {round(float(x["price"]), 4) for x in pools.get("equal_highs", [])}
            equal_low_prices = {round(float(x["price"]), 4) for x in pools.get("equal_lows", [])}

            signals: List[Dict[str, Any]] = []
            h4_trend = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            news_soon = bool(context.get("news_within_30m", False))
            displacement = context.get("displacement", {}).get(timeframe, [])
            disp_times = {
                pd.Timestamp(x.get("timestamp")).tz_convert(EASTERN) if pd.Timestamp(x.get("timestamp")).tzinfo else pd.Timestamp(x.get("timestamp")).tz_localize("UTC").tz_convert(EASTERN)
                for x in displacement
                if x.get("timestamp") is not None
            }

            threshold = 2 * self.tick_size
            for i in range(1, len(data) - 1):
                row = data.iloc[i]
                nxt = data.iloc[i + 1]
                ts = data.index[i].to_pydatetime()
                o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
                rng = max(h - l, 1e-9)
                up_wick = (h - max(o, c)) / rng
                dn_wick = (min(o, c) - l) / rng

                for lvl in bsl_levels:
                    swept = h >= lvl + threshold
                    closed_back = c < lvl or float(nxt["close"]) < lvl
                    body_opposite = c <= o
                    wick_ok = up_wick >= 0.30
                    if not (swept and closed_back and body_opposite and wick_ok):
                        continue

                    entry = float(nxt["close"]) if float(nxt["close"]) < lvl else c
                    stop = h + threshold
                    internal_swings = context.get("market_structure", {}).get(timeframe, {}).get("swings", {}).get("swing_lows", [])
                    downs = [float(x["price"]) for x in internal_swings if float(x["price"]) < entry]
                    t1 = max(downs) if downs else entry - 1.5 * (stop - entry)
                    next_ssl = [float(x["price"]) for x in context.get("liquidity_pools", {}).get(timeframe, {}).get("ssl_levels", []) if float(x["price"]) < entry]
                    t2 = max(next_ssl) if next_ssl else entry - 2.0 * (stop - entry)
                    opp_bsl = [float(x["price"]) for x in context.get("liquidity_pools", {}).get(timeframe, {}).get("bsl_levels", []) if float(x["price"]) > entry]
                    t3 = min(opp_bsl) if opp_bsl else t2

                    score = 0.60
                    confluences: List[str] = []
                    at_poi = self._at_ob_or_fvg(lvl, context, timeframe)
                    if at_poi:
                        score += 0.12
                        confluences.append("Sweep at OB/FVG level")
                    if round(lvl, 4) in equal_high_prices:
                        score += 0.10
                        confluences.append("Equal highs swept")
                    if self._is_kill_zone(ts):
                        score += 0.08
                        confluences.append("Kill zone timing")
                    if data.index[i + 1] in disp_times:
                        score += 0.08
                        confluences.append("Immediate displacement confirmation")
                    if h4_trend in {"BEARISH", "RANGING"}:
                        score += 0.05
                        confluences.append("HTF alignment")
                    else:
                        score -= 0.10
                        confluences.append("Counter-trend sweep")
                    if news_soon:
                        score -= 0.15
                        confluences.append("News risk within 30m")

                    if at_poi and self._is_kill_zone(ts) and round(lvl, 4) in equal_high_prices and data.index[i + 1] in disp_times:
                        score += 0.15
                        confluences.append("Highest-confidence setup stack")

                    score = max(0.0, min(1.0, score))
                    signals.append(
                        {
                            "strategy": "SWEEP_REVERSAL_SHORT",
                            "strategy_full_name": "Liquidity Sweep Reversal — Short",
                            "entry": float(entry),
                            "stop_loss": float(stop),
                            "target_1": float(t1),
                            "target_2": float(t2),
                            "target_3": float(t3),
                            "confidence": float(round(score, 2)),
                            "timeframe": timeframe,
                            "swept_level": float(lvl),
                            "confluence_factors": confluences,
                            "description": f"BSL sweep at {lvl:.2f} rejected; bearish reversal triggered.",
                        }
                    )

                for lvl in ssl_levels:
                    swept = l <= lvl - threshold
                    closed_back = c > lvl or float(nxt["close"]) > lvl
                    body_opposite = c >= o
                    wick_ok = dn_wick >= 0.30
                    if not (swept and closed_back and body_opposite and wick_ok):
                        continue

                    entry = float(nxt["close"]) if float(nxt["close"]) > lvl else c
                    stop = l - threshold
                    internal_swings = context.get("market_structure", {}).get(timeframe, {}).get("swings", {}).get("swing_highs", [])
                    ups = [float(x["price"]) for x in internal_swings if float(x["price"]) > entry]
                    t1 = min(ups) if ups else entry + 1.5 * (entry - stop)
                    next_bsl = [float(x["price"]) for x in context.get("liquidity_pools", {}).get(timeframe, {}).get("bsl_levels", []) if float(x["price"]) > entry]
                    t2 = min(next_bsl) if next_bsl else entry + 2.0 * (entry - stop)
                    opp_ssl = [float(x["price"]) for x in context.get("liquidity_pools", {}).get(timeframe, {}).get("ssl_levels", []) if float(x["price"]) < entry]
                    t3 = max(opp_ssl) if opp_ssl else t2

                    score = 0.60
                    confluences: List[str] = []
                    at_poi = self._at_ob_or_fvg(lvl, context, timeframe)
                    if at_poi:
                        score += 0.12
                        confluences.append("Sweep at OB/FVG level")
                    if round(lvl, 4) in equal_low_prices:
                        score += 0.10
                        confluences.append("Equal lows swept")
                    if self._is_kill_zone(ts):
                        score += 0.08
                        confluences.append("Kill zone timing")
                    if data.index[i + 1] in disp_times:
                        score += 0.08
                        confluences.append("Immediate displacement confirmation")
                    if h4_trend in {"BULLISH", "RANGING"}:
                        score += 0.05
                        confluences.append("HTF alignment")
                    else:
                        score -= 0.10
                        confluences.append("Counter-trend sweep")
                    if news_soon:
                        score -= 0.15
                        confluences.append("News risk within 30m")

                    if at_poi and self._is_kill_zone(ts) and round(lvl, 4) in equal_low_prices and data.index[i + 1] in disp_times:
                        score += 0.15
                        confluences.append("Highest-confidence setup stack")

                    score = max(0.0, min(1.0, score))
                    signals.append(
                        {
                            "strategy": "SWEEP_REVERSAL_LONG",
                            "strategy_full_name": "Liquidity Sweep Reversal — Long",
                            "entry": float(entry),
                            "stop_loss": float(stop),
                            "target_1": float(t1),
                            "target_2": float(t2),
                            "target_3": float(t3),
                            "confidence": float(round(score, 2)),
                            "timeframe": timeframe,
                            "swept_level": float(lvl),
                            "confluence_factors": confluences,
                            "description": f"SSL sweep at {lvl:.2f} rejected; bullish reversal triggered.",
                        }
                    )

            signals.sort(key=lambda x: x["confidence"], reverse=True)
            return signals
        except Exception as exc:
            logger.exception("detect_sweep_reversal failed: {}", exc)
            return []
