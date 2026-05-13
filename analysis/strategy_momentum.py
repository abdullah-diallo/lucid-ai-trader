"""
P08 Strategy A: Momentum Trading — ride strong directional moves in motion.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

try:
    from loguru import logger
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

EASTERN = pytz.timezone("US/Eastern")


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol     = df.get("volume", pd.Series(1, index=df.index))
    cum_tp_vol = (typical * vol).cumsum()
    cum_vol    = vol.cumsum().replace(0, float("nan"))
    return cum_tp_vol / cum_vol


def _swing_highs(series: pd.Series, window: int = 5) -> List[float]:
    highs: List[float] = []
    for i in range(window, len(series) - window):
        if series.iloc[i] == series.iloc[i - window:i + window + 1].max():
            highs.append(float(series.iloc[i]))
    return highs


class MomentumTradingStrategy:
    """Detect and enter strong directional momentum moves with tight risk management."""

    def __init__(self, tick_size: float = 0.25, max_hold_bars: int = 30) -> None:
        self.tick_size    = tick_size
        self.max_hold_bars = max_hold_bars

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ema_stack_confirmed(self, df: pd.DataFrame, direction: str) -> bool:
        """Check that 9/20/50 EMAs are cleanly stacked in the momentum direction."""
        if len(df) < 55:
            return False
        e9  = float(_ema(df["close"], 9).iloc[-1])
        e20 = float(_ema(df["close"], 20).iloc[-1])
        e50 = float(_ema(df["close"], 50).iloc[-1])
        if direction == "BULL":
            return e9 > e20 > e50
        if direction == "BEAR":
            return e9 < e20 < e50
        return False

    def _ema_sloping(self, df: pd.DataFrame, period: int, direction: str) -> bool:
        """Return True if the EMA is actively sloping in the momentum direction."""
        if len(df) < period + 3:
            return False
        e = _ema(df["close"], period)
        slope = float(e.iloc[-1]) - float(e.iloc[-4])
        return slope > 0 if direction == "BULL" else slope < 0

    def _rsi_value(self, df: pd.DataFrame) -> float:
        if len(df) < 15:
            return 50.0
        return float(_rsi(df["close"]).iloc[-1])

    def _rsi_ok(self, rsi: float, direction: str) -> bool:
        if direction == "BULL":
            return 60.0 <= rsi <= 75.0
        if direction == "BEAR":
            return 25.0 <= rsi <= 40.0
        return False

    def _recent_candles_aligned(self, df: pd.DataFrame, direction: str, count: int = 3) -> bool:
        """Check that the last `count` candles mostly close in the momentum direction."""
        if len(df) < count:
            return False
        tail = df.tail(count)
        bullish = (tail["close"] > tail["open"]).sum()
        bearish = (tail["close"] < tail["open"]).sum()
        if direction == "BULL":
            # Majority bullish and closing in upper half of range
            if bullish < 2:
                return False
            close_quality = all(
                (float(r["close"]) - float(r["low"])) / max(float(r["high"]) - float(r["low"]), self.tick_size) > 0.55
                for _, r in tail.iterrows()
            )
            return close_quality
        if direction == "BEAR":
            if bearish < 2:
                return False
            close_quality = all(
                (float(r["high"]) - float(r["close"])) / max(float(r["high"]) - float(r["low"]), self.tick_size) > 0.55
                for _, r in tail.iterrows()
            )
            return close_quality
        return False

    def _price_above_vwap(self, df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        vwap   = _vwap(df)
        close  = float(df["close"].iloc[-1])
        return close > float(vwap.iloc[-1])

    def _detect_ema_pullback(self, df: pd.DataFrame, direction: str) -> Optional[Dict[str, Any]]:
        """Detect a first-touch pullback to the 9 EMA after momentum established."""
        if len(df) < 25:
            return None
        e9    = _ema(df["close"], 9)
        close = df["close"]
        low   = df["low"]
        high  = df["high"]

        for i in range(-1, -6, -1):
            e9_val = float(e9.iloc[i])
            if direction == "BULL":
                # Low touched 9 EMA but close stayed above it
                if float(low.iloc[i]) <= e9_val * 1.001 and float(close.iloc[i]) >= e9_val:
                    return {
                        "entry_type":  "EMA_PULLBACK",
                        "entry_price": float(close.iloc[-1]),
                        "ema9_level":  round(e9_val, 4),
                    }
            elif direction == "BEAR":
                if float(high.iloc[i]) >= e9_val * 0.999 and float(close.iloc[i]) <= e9_val:
                    return {
                        "entry_type":  "EMA_PULLBACK",
                        "entry_price": float(close.iloc[-1]),
                        "ema9_level":  round(e9_val, 4),
                    }
        return None

    def _detect_flag_breakout(self, df: pd.DataFrame, direction: str) -> Optional[Dict[str, Any]]:
        """Detect a brief bull/bear flag (3-6 bar pause) followed by resumption candle."""
        if len(df) < 20:
            return None
        tail  = df.tail(8)
        close = tail["close"]
        high  = tail["high"]
        low   = tail["low"]

        # Identify a consolidation: tight range in last 3-5 bars
        last5 = df.tail(5)
        rng   = float(last5["high"].max()) - float(last5["low"].min())
        avg_rng = float((df["high"] - df["low"]).tail(20).mean())
        if rng > avg_rng * 0.7:
            return None  # Not tight enough — not a flag

        # Breakout candle (bar -1) breaks above flag
        breakout_bar = df.iloc[-1]
        prev_bar     = df.iloc[-2]
        if direction == "BULL":
            prev_high = float(last5["high"].iloc[:-1].max())
            if float(breakout_bar["close"]) > prev_high and float(breakout_bar["close"]) > float(breakout_bar["open"]):
                return {
                    "entry_type":  "FLAG_BREAKOUT",
                    "entry_price": float(breakout_bar["close"]),
                    "flag_high":   round(prev_high, 4),
                }
        elif direction == "BEAR":
            prev_low = float(last5["low"].iloc[:-1].min())
            if float(breakout_bar["close"]) < prev_low and float(breakout_bar["close"]) < float(breakout_bar["open"]):
                return {
                    "entry_type":  "FLAG_BREAKOUT",
                    "entry_price": float(breakout_bar["close"]),
                    "flag_low":    round(prev_low, 4),
                }
        return None

    def _compute_stops_targets(
        self,
        entry_price: float,
        direction: str,
        df: pd.DataFrame,
    ) -> Dict[str, float]:
        e20 = float(_ema(df["close"], 20).iloc[-1])
        if direction == "BULL":
            stop    = round(e20 - self.tick_size, 4)
            risk    = entry_price - stop
            target1 = round(entry_price + risk * 1.5, 4)
            swings  = _swing_highs(df["high"])
            target2 = next((h for h in sorted(swings) if h > entry_price + risk), round(entry_price + risk * 3.0, 4))
        else:
            stop    = round(e20 + self.tick_size, 4)
            risk    = stop - entry_price
            target1 = round(entry_price - risk * 1.5, 4)
            swings  = _swing_highs(df["low"])
            target2 = next((l for l in sorted(swings, reverse=True) if l < entry_price - risk), round(entry_price - risk * 3.0, 4))
        return {
            "stop":    stop,
            "risk":    round(abs(risk), 4),
            "target1": target1,
            "target2": round(target2, 4),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_momentum_setup(
        self,
        df: pd.DataFrame,
        context: dict,
        instrument: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Scan for a high-probability momentum entry. Returns a signal dict or None.

        Requires: aligned EMA stack, RSI in momentum range, recent candle alignment,
        and a valid entry (9 EMA pullback or bull/bear flag breakout).
        """
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_momentum.detect_momentum_setup"):
            return []
        try:
            data = _normalize_df(df)
            for col in ("open", "high", "low", "close"):
                if col not in data.columns:
                    return None
            if len(data) < 55:
                return None

            for direction in ("BULL", "BEAR"):
                # ── Gate 1: EMA stack ─────────────────────────────────────
                if not self._ema_stack_confirmed(data, direction):
                    continue

                # ── Gate 2: RSI in momentum range ─────────────────────────
                rsi = self._rsi_value(data)
                if not self._rsi_ok(rsi, direction):
                    continue

                # ── Gate 3: Recent candles aligned ────────────────────────
                if not self._recent_candles_aligned(data, direction):
                    continue

                # ── Gate 4: Price vs VWAP ─────────────────────────────────
                if direction == "BULL" and not self._price_above_vwap(data):
                    continue
                if direction == "BEAR" and self._price_above_vwap(data):
                    continue

                # ── Gate 5: 9 EMA still sloping ──────────────────────────
                if not self._ema_sloping(data, 9, direction):
                    continue

                # ── Entry selection ───────────────────────────────────────
                entry_info = self._detect_ema_pullback(data, direction)
                if entry_info is None:
                    entry_info = self._detect_flag_breakout(data, direction)
                if entry_info is None:
                    continue

                # ── Build signal ──────────────────────────────────────────
                sides     = {"BULL": ("MOMENTUM_LONG",  "BUY"),
                             "BEAR": ("MOMENTUM_SHORT", "SELL")}
                strategy, action = sides[direction]

                levels = self._compute_stops_targets(
                    entry_info["entry_price"], direction, data
                )

                # Confidence scoring
                score     = 0.55
                confluences: List[str] = ["EMA stack", "RSI momentum", "candle alignment"]

                htf_trend = str(
                    context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")
                ).upper()
                if (direction == "BULL" and htf_trend == "BULLISH") or \
                   (direction == "BEAR" and htf_trend == "BEARISH"):
                    score += 0.12
                    confluences.append("HTF 1H confluence")

                if entry_info["entry_type"] == "EMA_PULLBACK":
                    score += 0.08
                    confluences.append("9 EMA pullback entry")
                else:
                    score += 0.05
                    confluences.append("flag breakout entry")

                if self._price_above_vwap(data) and direction == "BULL":
                    score += 0.05
                    confluences.append("above VWAP")

                logger.info(
                    "MomentumStrategy: %s on %s | entry=%s | score=%.2f | %s",
                    strategy, instrument, entry_info["entry_price"], score, confluences,
                )

                return {
                    "strategy":            strategy,
                    "strategy_full_name":  f"Momentum Trend Ride — {'Long' if direction == 'BULL' else 'Short'}",
                    "action":              action,
                    "instrument":          instrument,
                    "direction":           direction,
                    "entry_price":         entry_info["entry_price"],
                    "entry_type":          entry_info["entry_type"],
                    "stop":                levels["stop"],
                    "risk":                levels["risk"],
                    "target1":             levels["target1"],
                    "target2":             levels["target2"],
                    "ema_stack_confirmed": True,
                    "rsi_value":           round(rsi, 2),
                    "max_hold_bars":       self.max_hold_bars,
                    "exit_rules": [
                        f"Exit if sideways for 6+ bars after entry",
                        f"Exit if 9 EMA flattens",
                        f"Trail stop to 9 EMA after Target 1 hit",
                        f"Hard time stop: {self.max_hold_bars} bars",
                    ],
                    "confidence":   round(min(score, 0.95), 3),
                    "confluence_factors": confluences,
                }

        except Exception as exc:
            logger.error("MomentumStrategy error: %s", exc)
        return None

    def should_exit_momentum(self, df: pd.DataFrame, direction: str, entry_bar_index: int) -> Dict[str, Any]:
        """
        Check real-time exit conditions after a momentum position is open.
        Returns dict with 'exit' bool and 'reason' string.
        """
        try:
            data = _normalize_df(df)
            bars_held = len(data) - entry_bar_index

            # Rule 1: time stop
            if bars_held >= self.max_hold_bars:
                return {"exit": True, "reason": "Max hold time reached"}

            # Rule 2: 9 EMA flattened
            if not self._ema_sloping(data, 9, direction):
                return {"exit": True, "reason": "9 EMA no longer sloping — momentum dead"}

            # Rule 3: sideways for 6 bars
            tail  = data.tail(6)
            rng   = float(tail["high"].max()) - float(tail["low"].min())
            avg_r = float((data["high"] - data["low"]).tail(20).mean())
            if rng < avg_r * 0.5:
                return {"exit": True, "reason": "6-bar sideways chop — momentum exhausted"}

            return {"exit": False, "reason": "Momentum intact"}
        except Exception as exc:
            return {"exit": False, "reason": str(exc)}
