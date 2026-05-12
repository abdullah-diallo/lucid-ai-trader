"""
Break of Structure entry strategy (P07).
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

from analysis.trading_concepts import EASTERN


class BOSEntryStrategy:
    """Implements BOS retest entry logic with HTF and confluence filters."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def _get_trend(self, context: dict, tf: str) -> str:
        """Return timeframe trend from context."""
        return str(context.get("market_structure", {}).get(tf, {}).get("trend", "RANGING")).upper()

    def _has_recent_choch(self, context: dict, tf: str, bars: int = 3) -> bool:
        """Check if timeframe recently printed CHoCH signal."""
        events = context.get("market_structure", {}).get(tf, {}).get("bos_choch", [])
        if not events:
            return False
        return any("CHOCH" in str(ev.get("type", "")) for ev in events[-bars:])

    def _latest_bos_event(self, context: dict, tf: str, direction: str, max_age_bars: int = 8) -> Optional[dict]:
        """Find latest BOS event in requested direction within max age bars."""
        events = context.get("market_structure", {}).get(tf, {}).get("bos_choch", [])
        if not events:
            return None
        key = "BOS_BULL" if direction == "BULLISH" else "BOS_BEAR"
        filtered = [e for e in events if e.get("type") == key]
        if not filtered:
            return None
        latest = filtered[-1]
        candle_index = int(latest.get("candle_index", -999))
        bars_count = int(context.get("meta", {}).get(f"{tf}_bars", 0))
        if bars_count and (bars_count - 1 - candle_index) > max_age_bars:
            return None
        return latest

    def _session_ok(self, current_dt: datetime) -> Dict[str, Any]:
        """Apply kill-zone/dead-zone timing rules."""
        et = current_dt.astimezone(EASTERN) if current_dt.tzinfo else pytz.utc.localize(current_dt).astimezone(EASTERN)
        t = et.time()
        london = t >= datetime.strptime("02:00", "%H:%M").time() and t < datetime.strptime("05:00", "%H:%M").time()
        ny_open = t >= datetime.strptime("07:00", "%H:%M").time() and t < datetime.strptime("10:00", "%H:%M").time()
        overlap = t >= datetime.strptime("08:00", "%H:%M").time() and t < datetime.strptime("12:00", "%H:%M").time()
        lunch = t >= datetime.strptime("12:00", "%H:%M").time() and t < datetime.strptime("14:00", "%H:%M").time()
        return {
            "is_kill_zone": london or ny_open or overlap,
            "is_dead_zone": lunch,
            "label": "OVERLAP" if overlap else ("NY_OPEN" if ny_open else ("LONDON" if london else "OTHER")),
        }

    def _retest_signal(
        self,
        entry_df: pd.DataFrame,
        bos_level: float,
        direction: str,
        bos_index: int,
        tolerance_pct: float = 0.0015,
    ) -> Optional[Dict[str, Any]]:
        """Find first valid rejection retest candle after BOS."""
        if bos_index >= len(entry_df) - 1:
            return None
        tol = bos_level * tolerance_pct
        search = entry_df.iloc[bos_index + 1 :].tail(8)
        for i in range(len(search)):
            row = search.iloc[i]
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            touch = (l <= bos_level + tol and h >= bos_level - tol)
            if direction == "BULLISH":
                valid_close = c >= bos_level
                rejection = l <= bos_level + tol and c >= o
            else:
                valid_close = c <= bos_level
                rejection = h >= bos_level - tol and c <= o
            if touch and valid_close and rejection:
                quality = "CLEAN" if abs(c - bos_level) <= (tol * 0.6) else "MESSY"
                return {"row": row, "quality": quality}
        return None

    def detect_bos_entry_setup(self, df_dict: dict, context: dict) -> list:
        """Detect BOS retest continuation entries with confluence scoring."""
        try:
            logger.info("Running BOS entry setup detection")
            signals: List[Dict[str, Any]] = []
            daily_trend = self._get_trend(context, "1D")
            h4_trend = self._get_trend(context, "4H")
            if daily_trend == "RANGING" or h4_trend != daily_trend or self._has_recent_choch(context, "4H"):
                return []

            direction = daily_trend
            current_dt = context.get("generated_at", datetime.now(tz=pytz.utc))
            session_state = self._session_ok(current_dt)
            news_soon = bool(context.get("news_within_30m", False))
            pd_zone = context.get("premium_discount", {}).get("zone", "EQUILIBRIUM")
            vwap_bias = context.get("vwap_position", {}).get("bias", "NEUTRAL")

            for tf in ("15m", "5m"):
                if tf not in df_dict or tf not in context.get("market_structure", {}):
                    continue
                entry_df = df_dict[tf].copy()
                if entry_df.empty:
                    continue
                context.setdefault("meta", {})[f"{tf}_bars"] = len(entry_df)
                bos_event = self._latest_bos_event(context, tf, direction, max_age_bars=8)
                if not bos_event:
                    continue
                bos_level = float(bos_event.get("price_level"))
                bos_idx = int(bos_event.get("candle_index", -1))
                retest = self._retest_signal(entry_df, bos_level, direction, bos_idx)
                if not retest:
                    continue

                row = retest["row"]
                entry = float(row["close"])
                if direction == "BULLISH":
                    stop = bos_level - (3 * self.tick_size)
                    t1 = entry + 1.5 * (entry - stop)
                    swings = context.get("market_structure", {}).get(tf, {}).get("swings", {}).get("swing_highs", [])
                    higher_swings = [float(x["price"]) for x in swings if float(x["price"]) > entry]
                    t2 = min(higher_swings) if higher_swings else entry + 2.0 * (entry - stop)
                    htf_bsl = context.get("liquidity_pools", {}).get("4H", {}).get("bsl_levels", [])
                    htf_targets = [float(x["price"]) for x in htf_bsl if float(x["price"]) > entry]
                    t3 = min(htf_targets) if htf_targets else t2
                    strategy = "BOS_LONG"
                    full_name = "Break of Structure — Long Entry"
                else:
                    stop = bos_level + (3 * self.tick_size)
                    t1 = entry - 1.5 * (stop - entry)
                    swings = context.get("market_structure", {}).get(tf, {}).get("swings", {}).get("swing_lows", [])
                    lower_swings = [float(x["price"]) for x in swings if float(x["price"]) < entry]
                    t2 = max(lower_swings) if lower_swings else entry - 2.0 * (stop - entry)
                    htf_ssl = context.get("liquidity_pools", {}).get("4H", {}).get("ssl_levels", [])
                    htf_targets = [float(x["price"]) for x in htf_ssl if float(x["price"]) < entry]
                    t3 = max(htf_targets) if htf_targets else t2
                    strategy = "BOS_SHORT"
                    full_name = "Break of Structure — Short Entry"

                confluences: List[str] = []
                score = 0.50

                if session_state["is_kill_zone"]:
                    score += 0.10
                    confluences.append("Kill zone timing")
                if session_state["is_dead_zone"]:
                    score -= 0.10
                    confluences.append("NY lunch dead zone")

                fvg_near = False
                all_fvgs = context.get("fvgs", {}).get(tf, {}).get("standard", [])
                for f in all_fvgs:
                    if abs(float(f.get("midpoint", 0.0)) - bos_level) / max(bos_level, 1e-9) <= 0.0015:
                        fvg_near = True
                        break
                if fvg_near:
                    score += 0.10
                    confluences.append("FVG at retest")

                ob_near = False
                for ob in context.get("order_blocks", {}).get(tf, {}).get("standard", []):
                    if float(ob.get("low", 0)) <= bos_level <= float(ob.get("high", 0)):
                        ob_near = True
                        break
                if ob_near:
                    score += 0.10
                    confluences.append("Order Block support/resistance")

                if (direction == "BULLISH" and vwap_bias == "BULLISH") or (direction == "BEARISH" and vwap_bias == "BEARISH"):
                    score += 0.05
                    confluences.append("VWAP aligned")

                if (direction == "BULLISH" and pd_zone == "DISCOUNT") or (direction == "BEARISH" and pd_zone == "PREMIUM"):
                    score += 0.05
                    confluences.append("Premium/discount aligned")

                h1_trend = self._get_trend(context, "1H")
                if h1_trend == direction:
                    score += 0.05
                    confluences.append("Daily/4H/1H agreement")

                if news_soon:
                    score -= 0.15
                    confluences.append("News risk within 30m")

                if "CHOCH" in str(bos_event.get("type", "")):
                    score -= 0.10
                    confluences.append("BOS came from CHoCH context")

                score = max(0.0, min(1.0, score))
                if score < 0.65:
                    continue

                rr1 = abs((t1 - entry) / (entry - stop)) if entry != stop else 0.0
                rr2 = abs((t2 - entry) / (entry - stop)) if entry != stop else 0.0
                timestamp = row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else current_dt

                signals.append(
                    {
                        "strategy": strategy,
                        "strategy_full_name": full_name,
                        "entry": float(entry),
                        "stop_loss": float(stop),
                        "target_1": float(t1),
                        "target_2": float(t2),
                        "target_3": float(t3),
                        "risk_reward_t1": float(round(rr1, 2)),
                        "risk_reward_t2": float(round(rr2, 2)),
                        "confidence": float(round(score, 2)),
                        "bos_level": float(bos_level),
                        "bos_timeframe": tf,
                        "retest_quality": retest["quality"],
                        "confluence_factors": confluences,
                        "invalidation_level": float(bos_level),
                        "timestamp": timestamp.astimezone(EASTERN) if timestamp.tzinfo else pytz.utc.localize(timestamp).astimezone(EASTERN),
                        "description": f"{full_name}: {tf} BOS retest held at {bos_level:.2f} with {len(confluences)} confluences.",
                    }
                )

            return signals
        except Exception as exc:
            logger.exception("detect_bos_entry_setup failed: {}", exc)
            return []
