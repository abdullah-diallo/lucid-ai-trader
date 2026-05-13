"""
backtesting/strategies.py
=========================
Self-contained strategy implementations for backtesting.
Each returns a list of signals: {"bar": int, "action": "BUY"|"SELL"|"CLOSE", "price": float, "reason": str}
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import numpy as np


Signal = Dict[str, Any]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP reset each calendar day."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, 1)
    cum_tpv = (tp * vol).groupby(df.index.date).cumsum()
    cum_vol  = vol.groupby(df.index.date).cumsum()
    return cum_tpv / cum_vol


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl  = df["high"] - df["low"]
    hpc = (df["high"] - df["close"].shift()).abs()
    lpc = (df["low"]  - df["close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Strategy registry ──────────────────────────────────────────────────────────

BACKTEST_STRATEGIES: Dict[str, Dict[str, Any]] = {}


def _register(name: str, label: str, description: str, markets: List[str]):
    def decorator(fn):
        BACKTEST_STRATEGIES[name] = {
            "name": name,
            "label": label,
            "description": description,
            "markets": markets,
            "fn": fn,
        }
        return fn
    return decorator


# ── ORB Breakout ──────────────────────────────────────────────────────────────

@_register("orb", "ORB Breakout", "Buy/sell breakout of the first 15-min opening range (9:30–9:45 ET)", ["futures", "stocks"])
def orb_strategy(df: pd.DataFrame, **params) -> List[Signal]:
    orb_minutes = params.get("orb_minutes", 15)
    signals: List[Signal] = []

    for date, day_df in df.groupby(df.index.date):
        rth = day_df.between_time("09:30", "16:00")
        if len(rth) < orb_minutes // 5 + 2:
            continue

        orb_window = rth.iloc[: orb_minutes // 5]
        orb_high   = orb_window["high"].max()
        orb_low    = orb_window["low"].min()
        post_orb   = rth.iloc[orb_minutes // 5:]

        long_triggered  = False
        short_triggered = False
        in_long  = False
        in_short = False

        for i, (ts, row) in enumerate(post_orb.iterrows()):
            bar_idx = df.index.get_loc(ts)

            if not long_triggered and row["high"] > orb_high:
                long_triggered = True
                if not in_long:
                    if in_short:
                        signals.append({"bar": bar_idx, "action": "CLOSE", "price": row["close"], "reason": "ORB flip short→long"})
                        in_short = False
                    signals.append({"bar": bar_idx, "action": "BUY", "price": row["close"], "reason": f"ORB breakout above {orb_high:.2f}"})
                    in_long = True

            elif not short_triggered and row["low"] < orb_low:
                short_triggered = True
                if not in_short:
                    if in_long:
                        signals.append({"bar": bar_idx, "action": "CLOSE", "price": row["close"], "reason": "ORB flip long→short"})
                        in_long = False
                    signals.append({"bar": bar_idx, "action": "SELL", "price": row["close"], "reason": f"ORB breakdown below {orb_low:.2f}"})
                    in_short = True

        # Close at end of day
        if in_long or in_short:
            last_ts  = rth.index[-1]
            last_bar = df.index.get_loc(last_ts)
            signals.append({"bar": last_bar, "action": "CLOSE", "price": rth["close"].iloc[-1], "reason": "EOD close"})

    return signals


# ── VWAP Mean Reversion ────────────────────────────────────────────────────────

@_register("vwap_reversion", "VWAP Reversion", "Buy below VWAP, sell above VWAP — mean-reversion to intraday average", ["futures", "stocks", "forex"])
def vwap_reversion_strategy(df: pd.DataFrame, **params) -> List[Signal]:
    threshold = params.get("threshold", 0.0015)  # 0.15% distance from VWAP
    signals: List[Signal] = []
    vwap = _vwap(df)
    in_long  = False
    in_short = False

    for i in range(1, len(df)):
        ts  = df.index[i]
        row = df.iloc[i]
        v   = vwap.iloc[i]
        if v == 0:
            continue

        dist = (row["close"] - v) / v

        # Only trade during RTH (9:30-16:00 ET)
        t = ts.time()
        from datetime import time as _time
        if not (_time(9, 30) <= t < _time(15, 45)):
            if in_long or in_short:
                signals.append({"bar": i, "action": "CLOSE", "price": row["close"], "reason": "EOD close"})
                in_long = in_short = False
            continue

        if dist < -threshold and not in_long:
            if in_short:
                signals.append({"bar": i, "action": "CLOSE", "price": row["close"], "reason": "VWAP flip"})
                in_short = False
            signals.append({"bar": i, "action": "BUY", "price": row["close"], "reason": f"Price {dist*100:.2f}% below VWAP"})
            in_long = True

        elif dist > threshold and not in_short:
            if in_long:
                signals.append({"bar": i, "action": "CLOSE", "price": row["close"], "reason": "VWAP flip"})
                in_long = False
            signals.append({"bar": i, "action": "SELL", "price": row["close"], "reason": f"Price {dist*100:.2f}% above VWAP"})
            in_short = True

        # Mean reversion target: price crosses back through VWAP
        elif in_long and dist > 0:
            signals.append({"bar": i, "action": "CLOSE", "price": row["close"], "reason": "VWAP reclaimed"})
            in_long = False
        elif in_short and dist < 0:
            signals.append({"bar": i, "action": "CLOSE", "price": row["close"], "reason": "VWAP reclaimed"})
            in_short = False

    return signals


# ── EMA Crossover ─────────────────────────────────────────────────────────────

@_register("ema_cross", "EMA Crossover", "Fast EMA crosses slow EMA — trend-following momentum strategy", ["futures", "forex", "stocks", "crypto"])
def ema_cross_strategy(df: pd.DataFrame, **params) -> List[Signal]:
    fast = params.get("fast_ema", 9)
    slow = params.get("slow_ema", 21)
    signals: List[Signal] = []
    fast_ema = _ema(df["close"], fast)
    slow_ema = _ema(df["close"], slow)
    in_long  = False
    in_short = False

    for i in range(slow + 1, len(df)):
        prev_cross = fast_ema.iloc[i - 1] - slow_ema.iloc[i - 1]
        curr_cross = fast_ema.iloc[i]     - slow_ema.iloc[i]
        price      = df["close"].iloc[i]
        bar        = i

        if prev_cross <= 0 and curr_cross > 0:  # Golden cross
            if in_short:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "EMA flip"})
                in_short = False
            if not in_long:
                signals.append({"bar": bar, "action": "BUY", "price": price,
                                 "reason": f"EMA{fast} crossed above EMA{slow}"})
                in_long = True

        elif prev_cross >= 0 and curr_cross < 0:  # Death cross
            if in_long:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "EMA flip"})
                in_long = False
            if not in_short:
                signals.append({"bar": bar, "action": "SELL", "price": price,
                                 "reason": f"EMA{fast} crossed below EMA{slow}"})
                in_short = True

    if in_long or in_short:
        signals.append({"bar": len(df) - 1, "action": "CLOSE",
                         "price": df["close"].iloc[-1], "reason": "End of data"})
    return signals


# ── Momentum Breakout ──────────────────────────────────────────────────────────

@_register("momentum", "Momentum Breakout", "Buy N-bar highs, sell N-bar lows — classic Donchian channel breakout", ["futures", "forex", "stocks"])
def momentum_strategy(df: pd.DataFrame, **params) -> List[Signal]:
    period   = params.get("period", 20)
    atr_mult = params.get("atr_stop", 2.0)
    signals: List[Signal] = []
    high_n   = df["high"].rolling(period).max()
    low_n    = df["low"].rolling(period).min()
    atr      = _atr(df)
    in_long  = False
    in_short = False
    entry_price = 0.0

    for i in range(period + 1, len(df)):
        price = df["close"].iloc[i]
        bar   = i
        prev_high = high_n.iloc[i - 1]
        prev_low  = low_n.iloc[i - 1]
        stop_dist = atr.iloc[i] * atr_mult

        if in_long:
            if price < entry_price - stop_dist:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "ATR stop hit"})
                in_long = False
        elif in_short:
            if price > entry_price + stop_dist:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "ATR stop hit"})
                in_short = False

        if df["high"].iloc[i] > prev_high and not in_long:
            if in_short:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "Breakout flip"})
                in_short = False
            signals.append({"bar": bar, "action": "BUY", "price": price,
                             "reason": f"{period}-bar high breakout"})
            in_long = True
            entry_price = price

        elif df["low"].iloc[i] < prev_low and not in_short:
            if in_long:
                signals.append({"bar": bar, "action": "CLOSE", "price": price, "reason": "Breakout flip"})
                in_long = False
            signals.append({"bar": bar, "action": "SELL", "price": price,
                             "reason": f"{period}-bar low breakdown"})
            in_short = True
            entry_price = price

    if in_long or in_short:
        signals.append({"bar": len(df) - 1, "action": "CLOSE",
                         "price": df["close"].iloc[-1], "reason": "End of data"})
    return signals
