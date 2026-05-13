"""
P09 Strategy B: Intraday Trend Following — EMA/VWAP/Structure pullback entries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from analysis.trading_concepts import EASTERN, _normalize_df


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _vwap_series(df: pd.DataFrame, context: dict) -> Optional[pd.Series]:
    raw = context.get("vwap_series")
    if raw is not None:
        return pd.Series(raw).reindex(df.index).ffill()
    val = context.get("vwap_value")
    if val is not None:
        return pd.Series(float(val), index=df.index)
    return None


class TrendFollowingStrategy:
    """
    Intraday trend following: find the dominant direction, wait for pullbacks,
    enter at EMA/VWAP/structure levels, and trail with the 9 EMA (P09-B).

    The hard rule: do not trade against the identified trend.
    The hard exit: a CHoCH ends the trade immediately.
    """

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    # ── Trend identification ──────────────────────────────────────────────────

    def identify_intraday_trend(self, context: dict, current_session: str) -> dict:
        """
        Determine today's intraday trend using a 5-factor hierarchy:
        1. Daily bias  2. 4H trend  3. VWAP position  4. 1H structure  5. EMA stack

        Returns a dict with intraday_trend, confidence, vwap_position,
        ema_stack, and trading_rule.
        """
        try:
            d   = str(context.get("market_structure", {}).get("1D",  {}).get("trend", "RANGING")).upper()
            h4  = str(context.get("market_structure", {}).get("4H",  {}).get("trend", "RANGING")).upper()
            h1  = str(context.get("market_structure", {}).get("1H",  {}).get("trend", "RANGING")).upper()

            price    = float(context.get("current_price", 0) or 0)
            vwap_val = context.get("vwap_value")
            vwap_position = "UNKNOWN"
            if vwap_val is not None and price:
                vwap_position = "ABOVE" if price > float(vwap_val) else "BELOW"

            ema9_val  = context.get("ema9_value")
            ema20_val = context.get("ema20_value")
            ema_stack = "UNKNOWN"
            if ema9_val is not None and ema20_val is not None:
                spread = float(ema9_val) - float(ema20_val)
                if spread > 0.5:
                    ema_stack = "BULL_FANNED"
                elif spread > 0:
                    ema_stack = "BULL"
                elif spread < -0.5:
                    ema_stack = "BEAR_FANNED"
                else:
                    ema_stack = "BEAR"

            # Weighted scoring — higher weight to slower timeframes
            bull = 0.0
            bear = 0.0

            # Daily bias: 2.0 pts
            if d == "BULLISH":
                bull += 2.0
            elif d == "BEARISH":
                bear += 2.0

            # 4H trend: 1.5 pts
            if h4 == "BULLISH":
                bull += 1.5
            elif h4 == "BEARISH":
                bear += 1.5

            # 1H structure: 1.0 pt
            if h1 == "BULLISH":
                bull += 1.0
            elif h1 == "BEARISH":
                bear += 1.0

            # VWAP position: 1.0 pt
            if vwap_position == "ABOVE":
                bull += 1.0
            elif vwap_position == "BELOW":
                bear += 1.0

            # EMA stack: 0.5 pt
            if "BULL" in ema_stack:
                bull += 0.5
            elif "BEAR" in ema_stack:
                bear += 0.5

            total = bull + bear
            confidence = round(max(bull, bear) / max(total, 1e-9), 2)
            net = bull - bear

            if net >= 4.0:
                intraday_trend = "STRONG_BULL"
                trading_rule   = "LONGS_ONLY"
            elif net >= 1.5:
                intraday_trend = "WEAK_BULL"
                trading_rule   = "LONGS_ONLY"
            elif net <= -4.0:
                intraday_trend = "STRONG_BEAR"
                trading_rule   = "SHORTS_ONLY"
            elif net <= -1.5:
                intraday_trend = "WEAK_BEAR"
                trading_rule   = "SHORTS_ONLY"
            else:
                intraday_trend = "NEUTRAL"
                trading_rule   = "AVOID" if current_session in {"LUNCH", "AFTER_HOURS", "ASIA"} else "BOTH"

            logger.info(
                "TrendFollowingStrategy: trend=%s confidence=%.2f rule=%s vwap=%s ema=%s",
                intraday_trend, confidence, trading_rule, vwap_position, ema_stack,
            )
            return {
                "intraday_trend": intraday_trend,
                "confidence":     confidence,
                "vwap_position":  vwap_position,
                "ema_stack":      ema_stack,
                "trading_rule":   trading_rule,
            }

        except Exception as exc:
            logger.exception("identify_intraday_trend failed: {}", exc)
            return {
                "intraday_trend": "NEUTRAL",
                "confidence":     0.0,
                "vwap_position":  "UNKNOWN",
                "ema_stack":      "UNKNOWN",
                "trading_rule":   "AVOID",
            }

    # ── Entry detection ───────────────────────────────────────────────────────

    def detect_trend_entry(
        self,
        df: pd.DataFrame,
        trend: dict,
        context: dict,
    ) -> dict | None:
        """
        Scan the DataFrame for the three valid trend-following entry types:
          TYPE 1 — EMA_PULLBACK:       price pulls to 20 EMA and bounces
          TYPE 2 — VWAP_PULLBACK:      price dips to VWAP and reclaims it
          TYPE 3 — STRUCTURE_PULLBACK: price retests a previous BOS/swing level

        Returns the first qualifying signal found, or None.
        Exits immediately on a CHoCH (9 EMA crosses 20 EMA opposite trend).
        After T1, trail the remaining position with the 9 EMA.
        """
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_trend_following.detect_trend_entry"):
            return []
        try:
            data = _normalize_df(df)
            if len(data) < 25:
                return None
            for col in ("open", "high", "low", "close"):
                if col not in data.columns:
                    return None

            trading_rule   = trend.get("trading_rule", "AVOID")
            intraday_trend = trend.get("intraday_trend", "NEUTRAL")
            if trading_rule == "AVOID":
                return None

            closes = data["close"].astype(float)
            highs  = data["high"].astype(float)
            lows   = data["low"].astype(float)

            ema9  = _ema(closes, 9)
            ema20 = _ema(closes, 20)
            ema50 = _ema(closes, 50)
            vwap  = _vwap_series(data, context)

            swing_highs = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
            swing_lows  = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows",  [])
            bsl_levels  = context.get("liquidity_pools", {}).get("5m", {}).get("bsl_levels", [])
            ssl_levels  = context.get("liquidity_pools", {}).get("5m", {}).get("ssl_levels", [])

            for i in range(20, len(data)):
                e9  = float(ema9.iloc[i])
                e20 = float(ema20.iloc[i])
                e50 = float(ema50.iloc[i])
                c   = float(closes.iloc[i])
                h   = float(highs.iloc[i])
                l   = float(lows.iloc[i])
                prev_c = float(closes.iloc[i - 1])
                prev_h = float(highs.iloc[i - 1])
                prev_l = float(lows.iloc[i - 1])

                # Resolve direction
                if trading_rule == "LONGS_ONLY":
                    direction = "LONG"
                elif trading_rule == "SHORTS_ONLY":
                    direction = "SHORT"
                else:
                    direction = "LONG" if e9 > e20 else "SHORT"

                # CHoCH guard — if EMA structure has flipped, the trend is over
                if direction == "LONG" and e9 < e20:
                    continue
                if direction == "SHORT" and e9 > e20:
                    continue

                entry_type: Optional[str] = None
                entry:      Optional[float] = None
                stop:       Optional[float] = None

                # ── TYPE 1: EMA PULLBACK ──────────────────────────────────
                if direction == "LONG":
                    touched_ema20 = prev_l <= e20 * 1.001
                    bounced       = c > prev_c and c > e20
                    if touched_ema20 and bounced:
                        entry_type = "EMA_PULLBACK"
                        entry      = c
                        stop       = e50 - self.tick_size

                elif direction == "SHORT":
                    touched_ema20 = prev_h >= e20 * 0.999
                    bounced       = c < prev_c and c < e20
                    if touched_ema20 and bounced:
                        entry_type = "EMA_PULLBACK"
                        entry      = c
                        stop       = e50 + self.tick_size

                # ── TYPE 2: VWAP PULLBACK ─────────────────────────────────
                if entry_type is None and vwap is not None:
                    v      = float(vwap.iloc[i])
                    prev_v = float(vwap.iloc[i - 1])
                    if direction == "LONG":
                        if prev_l <= prev_v and c > v:
                            entry_type = "VWAP_PULLBACK"
                            entry      = c
                            stop       = v - (2 * self.tick_size)
                    elif direction == "SHORT":
                        if prev_h >= prev_v and c < v:
                            entry_type = "VWAP_PULLBACK"
                            entry      = c
                            stop       = v + (2 * self.tick_size)

                # ── TYPE 3: STRUCTURE PULLBACK ────────────────────────────
                if entry_type is None:
                    if direction == "LONG" and swing_highs:
                        bos_candidates = [float(x["price"]) for x in swing_highs if float(x["price"]) < c]
                        if bos_candidates:
                            bos = max(bos_candidates)
                            if abs(l - bos) / max(abs(bos), 1e-9) <= 0.002 and c > bos:
                                entry_type = "STRUCTURE_PULLBACK"
                                entry      = c
                                stop       = bos - self.tick_size

                    elif direction == "SHORT" and swing_lows:
                        bos_candidates = [float(x["price"]) for x in swing_lows if float(x["price"]) > c]
                        if bos_candidates:
                            bos = min(bos_candidates)
                            if abs(h - bos) / max(abs(bos), 1e-9) <= 0.002 and c < bos:
                                entry_type = "STRUCTURE_PULLBACK"
                                entry      = c
                                stop       = bos + self.tick_size

                if entry_type is None or entry is None or stop is None:
                    continue

                risk = abs(entry - stop)
                if risk < self.tick_size:
                    continue

                # ── Targets ───────────────────────────────────────────────
                if direction == "LONG":
                    t1_pool = [float(x["price"]) for x in swing_highs if float(x["price"]) > entry]
                    t1      = min(t1_pool, default=entry + 1.5 * risk)
                    t2_pool = [float(x["price"]) for x in bsl_levels if float(x["price"]) > t1]
                    t2      = min(t2_pool, default=t1 + risk)
                else:
                    t1_pool = [float(x["price"]) for x in swing_lows if float(x["price"]) < entry]
                    t1      = max(t1_pool, default=entry - 1.5 * risk)
                    t2_pool = [float(x["price"]) for x in ssl_levels if float(x["price"]) < t1]
                    t2      = max(t2_pool, default=t1 - risk)

                ts       = data.index[i].to_pydatetime()
                strategy = f"TREND_FOLLOW_{'LONG' if direction == 'LONG' else 'SHORT'}"

                logger.info(
                    "TrendFollowingStrategy: %s via %s | entry=%.4f stop=%.4f t1=%.4f t2=%.4f",
                    strategy, entry_type, entry, stop, t1, t2,
                )

                return {
                    "strategy":           strategy,
                    "strategy_full_name": f"Intraday Trend Following — {'Long' if direction == 'LONG' else 'Short'} with Trend",
                    "entry":              float(entry),
                    "stop_loss":          float(stop),
                    "target_1":           float(t1),
                    "target_2":           float(t2),
                    "entry_type":         entry_type,
                    "trend_strength":     intraday_trend,
                    "trailing_stop_ema":  9,
                    "partial_exit": {
                        "at_target_1_pct": 0.50,
                        "trail_remainder_with": "9_EMA",
                        "exit_trigger":    "9_EMA_cross_20_EMA or close_below_VWAP",
                        "choch_rule":      "Exit immediately on CHoCH — trend is over",
                    },
                    "exit_rules": [
                        "9 EMA crosses 20 EMA opposite direction → exit full position",
                        "Price closes beyond VWAP against the trade → exit",
                        "CHoCH detected → exit immediately, no exceptions",
                        "Take 50% off at T1, trail remaining with 9 EMA",
                    ],
                    "confidence":  float(round(trend.get("confidence", 0.5), 2)),
                    "timestamp":   ts.isoformat(),
                    "description": (
                        f"Trend follow {'long' if direction == 'LONG' else 'short'} via {entry_type} "
                        f"at {entry:.2f}. Trend: {intraday_trend}. "
                        f"T1={t1:.2f} (take 50%), T2={t2:.2f} (trail 9 EMA). "
                        f"Stop={stop:.2f}. Exit on CHoCH or VWAP loss."
                    ),
                }

        except Exception as exc:
            logger.exception("detect_trend_entry failed: {}", exc)
        return None
