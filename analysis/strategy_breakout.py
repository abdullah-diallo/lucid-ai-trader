"""
P08 Strategy B: Breakout Trading — enter when price breaks a key level with conviction.
"""

from __future__ import annotations

from datetime import time
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

# Minimum pts close beyond level to qualify as a real breakout (MES default)
MIN_BREAKOUT_CLEARANCE = 0.75
# Minimum bars of consolidation near a level before breakout is meaningful
MIN_CONSOLIDATION_BARS = 5
# Minimum number of prior level tests before it qualifies
MIN_TEST_COUNT = 2


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl  = df["high"] - df["low"]
    hpc = (df["high"] - df["close"].shift()).abs()
    lpc = (df["low"]  - df["close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _is_kill_zone(dt) -> bool:
    """London (02-05 ET) and NY (07-10 ET) kill zones — highest breakout probability."""
    try:
        if hasattr(dt, "tzinfo") and dt.tzinfo:
            et = dt.astimezone(EASTERN)
        else:
            et = EASTERN.localize(dt)
        t = et.time()
        return (time(2, 0) <= t < time(5, 0)) or (time(7, 0) <= t < time(10, 0))
    except Exception:
        return False


def _find_key_levels(df: pd.DataFrame, lookback: int = 60, tolerance_pct: float = 0.001) -> List[Dict[str, Any]]:
    """
    Identify horizontal price levels that have been tested at least MIN_TEST_COUNT times.
    Returns list of {level, test_count, level_type, last_tested_bar}.
    """
    if len(df) < lookback:
        return []

    data     = df.tail(lookback)
    highs    = data["high"].values
    lows     = data["low"].values
    closes   = data["close"].values
    n        = len(data)

    # Collect swing highs and lows as candidate levels
    candidates: List[float] = []
    for i in range(2, n - 2):
        if highs[i] >= highs[i-1] and highs[i] >= highs[i-2] and highs[i] >= highs[i+1] and highs[i] >= highs[i+2]:
            candidates.append(float(highs[i]))
        if lows[i] <= lows[i-1] and lows[i] <= lows[i-2] and lows[i] <= lows[i+1] and lows[i] <= lows[i+2]:
            candidates.append(float(lows[i]))

    # Add session open/prior session high-low context if available
    try:
        daily_high = float(data["high"].max())
        daily_low  = float(data["low"].min())
        candidates += [daily_high, daily_low]
    except Exception:
        pass

    if not candidates:
        return []

    # Cluster nearby candidates into single levels
    candidates = sorted(set(candidates))
    levels: List[Dict[str, Any]] = []
    used = set()

    for ci, cand in enumerate(candidates):
        if ci in used:
            continue
        cluster = [cand]
        for cj, other in enumerate(candidates):
            if cj != ci and cj not in used:
                if abs(other - cand) / max(abs(cand), 1e-6) < tolerance_pct * 3:
                    cluster.append(other)
                    used.add(cj)
        used.add(ci)
        level_price = sum(cluster) / len(cluster)

        # Count actual bar touches at this level
        tol  = level_price * tolerance_pct
        test_count = 0
        last_bar   = 0
        for bi in range(n):
            h = float(highs[bi])
            l = float(lows[bi])
            if l <= level_price + tol and h >= level_price - tol:
                test_count += 1
                last_bar    = bi

        if test_count < MIN_TEST_COUNT:
            continue

        # Classify level type
        recent_close = float(closes[-1])
        if abs(level_price - float(data["high"].max())) / max(level_price, 1e-6) < 0.002:
            level_type = "daily high"
        elif abs(level_price - float(data["low"].min())) / max(level_price, 1e-6) < 0.002:
            level_type = "daily low"
        elif level_price > recent_close:
            level_type = "resistance"
        else:
            level_type = "support"

        levels.append({
            "level":         round(level_price, 4),
            "test_count":    test_count,
            "level_type":    level_type,
            "last_tested_bar": last_bar,
        })

    return sorted(levels, key=lambda x: x["test_count"], reverse=True)


def _consolidation_bars_near_level(df: pd.DataFrame, level: float, tolerance: float = 0.75) -> int:
    """Count consecutive bars that stayed within `tolerance` pts of the level."""
    count = 0
    for i in range(len(df) - 1, -1, -1):
        bar = df.iloc[i]
        if (float(bar["high"]) - float(bar["low"])) <= tolerance * 3:
            if abs(float(bar["close"]) - level) <= tolerance * 2:
                count += 1
            else:
                break
        else:
            break
    return count


def _is_breakout_candle_strong(df: pd.DataFrame) -> bool:
    """Check if the most recent candle is larger than the 10-bar average."""
    if len(df) < 11:
        return False
    recent_body = abs(float(df["close"].iloc[-1]) - float(df["open"].iloc[-1]))
    avg_body    = (df["close"] - df["open"]).abs().tail(11).iloc[:-1].mean()
    return recent_body > float(avg_body)


def _has_bearish_fvg_above(context: dict, level: float, direction: str) -> bool:
    """Return True if there's an opposing FVG that could act as a ceiling/floor."""
    if direction != "LONG":
        return False
    fvgs = context.get("fvgs", {})
    for tf_data in fvgs.values():
        for fvg in tf_data.get("standard", []):
            fvg_top = fvg.get("top", 0)
            fvg_bot = fvg.get("bottom", 0)
            if fvg_bot > level and fvg_bot < level * 1.005:
                return True
    return False


def _htf_confirms(context: dict, direction: str) -> tuple[bool, bool]:
    """
    Returns (confirms, opposes).
    confirms = HTF trend matches breakout direction.
    opposes  = HTF trend is strongly opposite (breakout may be a trap).
    """
    h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
    h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()

    if direction == "LONG":
        confirms = h4 in ("BULLISH",) or h1 in ("BULLISH",)
        opposes  = h4 == "BEARISH" and h1 == "BEARISH"
    else:
        confirms = h4 in ("BEARISH",) or h1 in ("BEARISH",)
        opposes  = h4 == "BULLISH" and h1 == "BULLISH"

    return confirms, opposes


class BreakoutTradingStrategy:
    """
    Detect price breakouts through tested key levels, with false-breakout filtering
    and dual-entry options (momentum close or retest).
    """

    def __init__(self, tick_size: float = 0.25, min_clearance: float = MIN_BREAKOUT_CLEARANCE) -> None:
        self.tick_size     = tick_size
        self.min_clearance = min_clearance

    def detect_breakout(self, df: pd.DataFrame, context: dict) -> List[Dict[str, Any]]:
        """
        Scan for valid breakout setups on the given bar data.

        Returns a list of signal dicts (usually 0 or 1 entries per bar).
        Each dict contains the full breakout signal with both entry options,
        confidence score, false-breakout flags, and exit levels.
        """
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_breakout.detect_breakout"):
            return []
        signals: List[Dict[str, Any]] = []
        try:
            data = _normalize_df(df)
            for col in ("open", "high", "low", "close"):
                if col not in data.columns:
                    return []
            if len(data) < 30:
                return []

            current_close = float(data["close"].iloc[-1])
            current_open  = float(data["open"].iloc[-1])
            current_high  = float(data["high"].iloc[-1])
            current_low   = float(data["low"].iloc[-1])
            candle_bull   = current_close > current_open

            atr_val = float(_atr(data).iloc[-1]) if len(data) >= 15 else 2.0

            # ── Find candidate key levels ─────────────────────────────────
            levels = _find_key_levels(data)
            if not levels:
                return []

            last_ts = data.index[-1]
            in_kill_zone = _is_kill_zone(last_ts)

            for lvl in levels:
                level_price  = lvl["level"]
                level_type   = lvl["level_type"]
                test_count   = lvl["test_count"]

                # ── Determine breakout direction ──────────────────────────
                if current_close > level_price + self.min_clearance:
                    direction = "LONG"
                    strategy  = "BREAKOUT_LONG"
                    action    = "BUY"
                elif current_close < level_price - self.min_clearance:
                    direction = "SHORT"
                    strategy  = "BREAKOUT_SHORT"
                    action    = "SELL"
                else:
                    continue  # Not broken yet

                # Candle must close in breakout direction
                if direction == "LONG"  and not candle_bull:
                    continue
                if direction == "SHORT" and candle_bull:
                    continue

                # ── Gate: consolidation bars near level ───────────────────
                consol_bars = _consolidation_bars_near_level(data, level_price)
                if consol_bars < MIN_CONSOLIDATION_BARS:
                    continue

                # ── Gate: breakout candle size ────────────────────────────
                candle_strong = _is_breakout_candle_strong(data)

                # ── Confidence scoring ────────────────────────────────────
                score        = 0.50
                confluences: List[str] = []
                false_break_warnings: List[str] = []

                # Test count bonus
                if test_count >= 3:
                    score += 0.08
                    confluences.append(f"Level tested {test_count}x (strong compression)")
                else:
                    score += 0.04
                    confluences.append(f"Level tested {test_count}x")

                # Consolidation
                if consol_bars >= 8:
                    score += 0.08
                    confluences.append(f"{consol_bars} bars consolidation (coiling)")
                elif consol_bars >= MIN_CONSOLIDATION_BARS:
                    score += 0.04
                    confluences.append(f"{consol_bars} bars near level")

                # Candle strength
                if candle_strong:
                    score += 0.07
                    confluences.append("Breakout candle above avg size")
                else:
                    score -= 0.03

                # Kill zone
                if in_kill_zone:
                    score += 0.08
                    confluences.append("Kill zone timing")

                # HTF structure
                htf_confirms, htf_opposes = _htf_confirms(context, direction)
                if htf_confirms:
                    score += 0.10
                    confluences.append("HTF trend confirms breakout")
                if htf_opposes:
                    score -= 0.15
                    false_break_warnings.append("HTF trend opposing — possible trap")

                # Opposing FVG check
                if _has_bearish_fvg_above(context, level_price, direction):
                    score -= 0.12
                    false_break_warnings.append("Bearish FVG above breakout level — potential ceiling")

                # Prior session high/daily high bonus
                if "daily" in level_type or "session" in level_type:
                    score += 0.06
                    confluences.append(f"Key level: {level_type}")

                score = round(min(max(score, 0.10), 0.95), 3)

                if score < 0.40:
                    continue  # Skip low-confidence setups

                # ── Entry options ─────────────────────────────────────────
                # Option A: momentum — enter on this candle's close
                entry_a = current_close

                # Option B: retest — wait for price to pull back to broken level
                entry_b = level_price + (self.tick_size if direction == "LONG" else -self.tick_size)

                entry_option = "A_MOMENTUM" if candle_strong else "B_RETEST"

                # ── Risk levels ───────────────────────────────────────────
                if direction == "LONG":
                    stop      = round(level_price - atr_val * 0.5, 4)
                    entry_use = entry_a if entry_option == "A_MOMENTUM" else entry_b
                    risk      = entry_use - stop
                    target1   = round(entry_use + risk * 1.5, 4)
                    target2   = round(entry_use + risk * 3.0, 4)
                else:
                    stop      = round(level_price + atr_val * 0.5, 4)
                    entry_use = entry_a if entry_option == "A_MOMENTUM" else entry_b
                    risk      = stop - entry_use
                    target1   = round(entry_use - risk * 1.5, 4)
                    target2   = round(entry_use - risk * 3.0, 4)

                risk = round(abs(risk), 4)

                logger.info(
                    "BreakoutStrategy: %s | level=%s (%s) | tests=%d | consol=%d bars | score=%.2f | entry=%s",
                    strategy, level_price, level_type, test_count, consol_bars, score, entry_option,
                )

                signals.append({
                    "strategy":              strategy,
                    "strategy_full_name":    f"Breakout Through Key Level — {'Long' if direction == 'LONG' else 'Short'}",
                    "action":                action,
                    "direction":             direction,
                    "level_price":           level_price,
                    "level_type":            level_type,
                    "test_count":            test_count,
                    "consolidation_bars":    consol_bars,
                    "breakout_clearance":    round(abs(current_close - level_price), 4),
                    "candle_strong":         candle_strong,
                    "in_kill_zone":          in_kill_zone,
                    "entry_option":          entry_option,
                    "entry_A_momentum":      round(entry_a, 4),
                    "entry_B_retest":        round(entry_b, 4),
                    "entry_recommended":     round(entry_use, 4),
                    "stop":                  stop,
                    "risk":                  risk,
                    "target1":               target1,
                    "target2":               target2,
                    "confidence":            score,
                    "confluence_factors":     confluences,
                    "false_break_warnings":  false_break_warnings,
                    "entry_note": (
                        "Strong candle — enter on close (Option A)" if entry_option == "A_MOMENTUM"
                        else "Moderate candle — wait for retest of broken level (Option B)"
                    ),
                })

        except Exception as exc:
            logger.error("BreakoutStrategy error: %s", exc)

        return signals

    def is_retest_entry_valid(self, df: pd.DataFrame, level: float, direction: str) -> bool:
        """
        After a breakout, check if price has pulled back to the broken level
        and is showing rejection (confirming the retest entry trigger).
        """
        try:
            data = _normalize_df(df)
            if len(data) < 3:
                return False
            last_bar = data.iloc[-1]
            tol = self.tick_size * 3
            near_level = abs(float(last_bar["low" if direction == "LONG" else "high"]) - level) <= tol
            rejection = (
                float(last_bar["close"]) > float(last_bar["open"])  # bull rejection
                if direction == "LONG"
                else float(last_bar["close"]) < float(last_bar["open"])  # bear rejection
            )
            return near_level and rejection
        except Exception:
            return False
