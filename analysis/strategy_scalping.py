"""
P09 Strategy A: Scalping — high-frequency small-target trades at micro POIs during kill zones.
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

# ── Instrument defaults ───────────────────────────────────────────────────────
INSTRUMENT_PARAMS: Dict[str, Dict[str, float]] = {
    "MES": {"target1": 1.5, "target2": 3.0, "stop": 1.0, "tick": 0.25},
    "MNQ": {"target1": 6.0, "target2": 12.0, "stop": 4.0, "tick": 0.25},
}
DEFAULT_PARAMS = {"target1": 1.5, "target2": 3.0, "stop": 1.0, "tick": 0.25}

# ── Session kill zones (ET) ───────────────────────────────────────────────────
KILL_ZONES: List[tuple] = [
    (time(2, 0),  time(5, 0)),   # London open
    (time(7, 0),  time(10, 0)),  # NY open
    (time(9, 30), time(11, 30)), # NY RTH early session
]
NO_SCALP_ZONES: List[tuple] = [
    (time(11, 30), time(13, 30)),  # NY lunch — low volume
    (time(16, 0),  time(20, 0)),   # After hours
    (time(20, 0),  time(2, 0)),    # Asia — thin volume
]


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


def _in_kill_zone(dt) -> bool:
    try:
        et = dt.astimezone(EASTERN) if getattr(dt, "tzinfo", None) else EASTERN.localize(dt)
        t  = et.time()
        for start, end in KILL_ZONES:
            if start <= t < end:
                return True
        return False
    except Exception:
        return False


def _in_no_scalp_zone(dt) -> bool:
    try:
        et = dt.astimezone(EASTERN) if getattr(dt, "tzinfo", None) else EASTERN.localize(dt)
        t  = et.time()
        # Handle overnight no-scalp (20:00 – 02:00)
        if t >= time(20, 0) or t < time(2, 0):
            return True
        for start, end in NO_SCALP_ZONES:
            if start <= t < end:
                return True
        return False
    except Exception:
        return True  # fail safe — don't scalp if can't determine time


def _get_5m_trend(df_5m: pd.DataFrame) -> str:
    """Fast 5m trend using EMA 9/20 slope."""
    if len(df_5m) < 22:
        return "NEUTRAL"
    e9  = float(_ema(df_5m["close"], 9).iloc[-1])
    e20 = float(_ema(df_5m["close"], 20).iloc[-1])
    close = float(df_5m["close"].iloc[-1])
    if e9 > e20 and close > e9:
        return "BULL"
    if e9 < e20 and close < e9:
        return "BEAR"
    return "NEUTRAL"


def _detect_micro_fvg(df_1m: pd.DataFrame, direction: str) -> Optional[Dict[str, Any]]:
    """Detect a fresh 1-minute Fair Value Gap within the last 6 bars."""
    if len(df_1m) < 7:
        return None
    for i in range(-2, -7, -1):
        try:
            bar_a = df_1m.iloc[i - 1]
            bar_b = df_1m.iloc[i]
            bar_c = df_1m.iloc[i + 1] if i + 1 < 0 else df_1m.iloc[-1]
            if direction == "BULL":
                # Bullish FVG: bar_c low > bar_a high
                if float(bar_c["low"]) > float(bar_a["high"]):
                    fvg_top = float(bar_c["low"])
                    fvg_bot = float(bar_a["high"])
                    current_price = float(df_1m["close"].iloc[-1])
                    if fvg_bot <= current_price <= fvg_top * 1.002:
                        return {"type": "FVG", "top": fvg_top, "bottom": fvg_bot,
                                "poi": round((fvg_top + fvg_bot) / 2, 4)}
            elif direction == "BEAR":
                # Bearish FVG: bar_c high < bar_a low
                if float(bar_c["high"]) < float(bar_a["low"]):
                    fvg_top = float(bar_a["low"])
                    fvg_bot = float(bar_c["high"])
                    current_price = float(df_1m["close"].iloc[-1])
                    if fvg_bot * 0.998 <= current_price <= fvg_top:
                        return {"type": "FVG", "top": fvg_top, "bottom": fvg_bot,
                                "poi": round((fvg_top + fvg_bot) / 2, 4)}
        except (IndexError, KeyError):
            continue
    return None


def _detect_micro_order_block(df_1m: pd.DataFrame, direction: str) -> Optional[Dict[str, Any]]:
    """Detect a 1-minute order block (last opposing candle before impulse)."""
    if len(df_1m) < 8:
        return None
    try:
        # Find the last impulse move then look back at the last opposing candle
        close = df_1m["close"]
        opens = df_1m["open"]
        for i in range(-2, -8, -1):
            candle_bull = float(close.iloc[i]) > float(opens.iloc[i])
            if direction == "BULL" and not candle_bull:
                ob_high = float(df_1m["high"].iloc[i])
                ob_low  = float(df_1m["low"].iloc[i])
                current = float(df_1m["close"].iloc[-1])
                if ob_low <= current <= ob_high:
                    return {"type": "ORDER_BLOCK", "top": ob_high, "bottom": ob_low,
                            "poi": round((ob_high + ob_low) / 2, 4)}
            elif direction == "BEAR" and candle_bull:
                ob_high = float(df_1m["high"].iloc[i])
                ob_low  = float(df_1m["low"].iloc[i])
                current = float(df_1m["close"].iloc[-1])
                if ob_low <= current <= ob_high:
                    return {"type": "ORDER_BLOCK", "top": ob_high, "bottom": ob_low,
                            "poi": round((ob_high + ob_low) / 2, 4)}
    except (IndexError, KeyError):
        pass
    return None


def _detect_micro_bos(df_1m: pd.DataFrame, direction: str) -> Optional[Dict[str, Any]]:
    """Detect a micro Break of Structure on the 1m chart (last 10 bars)."""
    if len(df_1m) < 12:
        return None
    try:
        tail  = df_1m.tail(12)
        highs = tail["high"].values
        lows  = tail["low"].values
        n     = len(highs)
        if direction == "BULL":
            # BOS: current high exceeds the swing high from 3-8 bars ago
            swing_high = float(max(highs[2:9]))
            current    = float(df_1m["close"].iloc[-1])
            if current > swing_high:
                return {"type": "MICRO_BOS", "broken_level": round(swing_high, 4),
                        "poi": round(swing_high, 4)}
        elif direction == "BEAR":
            swing_low = float(min(lows[2:9]))
            current   = float(df_1m["close"].iloc[-1])
            if current < swing_low:
                return {"type": "MICRO_BOS", "broken_level": round(swing_low, 4),
                        "poi": round(swing_low, 4)}
    except (IndexError, ValueError):
        pass
    return None


def _min_rr_met(entry: float, stop: float, target: float) -> bool:
    risk   = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return False
    return (reward / risk) >= 1.5


class ScalpingStrategy:
    """
    High-frequency scalping on 1m bars during kill zones only.
    Uses micro FVGs, order blocks, and 1m BOS as entry triggers.
    All entries require 5m trend alignment and minimum 1.5:1 R:R.
    """

    def __init__(self, instrument: str = "MES", max_daily_scalps: int = 2, protected_mode: bool = False) -> None:
        self.instrument     = instrument.upper()
        self.max_daily_scalps = max_daily_scalps
        self.protected_mode = protected_mode
        self._params        = INSTRUMENT_PARAMS.get(self.instrument, DEFAULT_PARAMS)
        self._daily_scalp_count = 0
        self._daily_loss_pct    = 0.0

    # ── State management ──────────────────────────────────────────────────────

    def reset_daily_state(self) -> None:
        """Call at the start of each trading session."""
        self._daily_scalp_count = 0
        self._daily_loss_pct    = 0.0

    def record_trade_result(self, pnl: float, daily_loss_limit: float) -> None:
        """Update internal counters after each closed scalp trade."""
        self._daily_scalp_count += 1
        if pnl < 0 and daily_loss_limit > 0:
            self._daily_loss_pct += abs(pnl) / daily_loss_limit

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_scalp_setup(
        self,
        df_1m: pd.DataFrame,
        df_5m: pd.DataFrame,
        context: dict,
    ) -> List[Dict[str, Any]]:
        """
        Scan 1m bars for scalp entries during kill zones with 5m trend alignment.

        Returns a list of scalp signal dicts (0 or 1 per call).
        Each signal includes instrument-specific targets, stop, POI type,
        session validity flag, and all active risk management constraints.
        """
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df_1m, min_bars=30, caller="strategy_scalping.detect_scalp_setup"):
            return []
        signals: List[Dict[str, Any]] = []
        try:
            data_1m = _normalize_df(df_1m)
            data_5m = _normalize_df(df_5m)
            for col in ("open", "high", "low", "close"):
                if col not in data_1m.columns or col not in data_5m.columns:
                    return []
            if len(data_1m) < 15 or len(data_5m) < 22:
                return []

            last_ts      = data_1m.index[-1]
            session_valid = _in_kill_zone(last_ts) and not _in_no_scalp_zone(last_ts)

            # ── Gate 1: kill zone ─────────────────────────────────────────
            if not session_valid:
                return []

            # ── Gate 2: prop firm protection ─────────────────────────────
            if self.protected_mode:
                if self._daily_scalp_count >= self.max_daily_scalps:
                    logger.info("ScalpingStrategy: max daily scalps reached (%d)", self.max_daily_scalps)
                    return []
                if self._daily_loss_pct >= 0.50:
                    logger.info("ScalpingStrategy: DLL 50%% hit — scalping suspended")
                    return []

            # ── Gate 3: 5m trend ─────────────────────────────────────────
            trend_5m = _get_5m_trend(data_5m)
            if trend_5m == "NEUTRAL":
                return []

            direction = trend_5m  # BULL or BEAR
            action    = "BUY" if direction == "BULL" else "SELL"
            strategy  = "SCALP_LONG" if direction == "BULL" else "SCALP_SHORT"

            # ── Gate 4: micro POI on 1m ───────────────────────────────────
            poi = (
                _detect_micro_fvg(data_1m, direction)
                or _detect_micro_order_block(data_1m, direction)
                or _detect_micro_bos(data_1m, direction)
            )
            if poi is None:
                return []

            # ── Gate 5: entry must be at a known level ────────────────────
            entry_price = poi["poi"]
            p           = self._params
            stop_pts    = p["stop"]
            target1_pts = p["target1"]
            target2_pts = p["target2"]

            stop    = round(entry_price - stop_pts if direction == "BULL" else entry_price + stop_pts, 4)
            target1 = round(entry_price + target1_pts if direction == "BULL" else entry_price - target1_pts, 4)
            target2 = round(entry_price + target2_pts if direction == "BULL" else entry_price - target2_pts, 4)

            # ── Gate 6: minimum 1.5:1 R:R ────────────────────────────────
            if not _min_rr_met(entry_price, stop, target1):
                return []

            # Confidence
            score        = 0.55
            confluences: List[str] = []

            if trend_5m == "BULL":
                score += 0.07
                confluences.append("5m bullish trend")
            else:
                score += 0.07
                confluences.append("5m bearish trend")

            poi_type = poi.get("type", "UNKNOWN")
            if poi_type == "FVG":
                score += 0.10
                confluences.append("1m Micro FVG entry")
            elif poi_type == "ORDER_BLOCK":
                score += 0.08
                confluences.append("1m Micro Order Block")
            elif poi_type == "MICRO_BOS":
                score += 0.06
                confluences.append("1m Micro BOS break")

            htf = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
            if (direction == "BULL" and htf == "BULLISH") or (direction == "BEAR" and htf == "BEARISH"):
                score += 0.08
                confluences.append("1H trend aligned")

            score = round(min(score, 0.92), 3)

            logger.info(
                "ScalpingStrategy: %s | %s poi=%s | entry=%.4f stop=%.4f t1=%.4f | score=%.2f",
                strategy, poi_type, entry_price, entry_price, stop, target1, score,
            )

            signals.append({
                "strategy":           strategy,
                "strategy_full_name": f"1-Minute Scalp — {'Long' if direction == 'BULL' else 'Short'} at Micro POI",
                "action":             action,
                "direction":          direction,
                "instrument":         self.instrument,
                "entry_price":        entry_price,
                "poi_type":           poi_type,
                "poi_details":        poi,
                "stop":               stop,
                "target1":            target1,
                "target2":            target2,
                "scalp_stop_pts":     stop_pts,
                "scalp_target_pts":   target1_pts,
                "session_valid":      session_valid,
                "trend_5m":           trend_5m,
                "daily_scalp_count":  self._daily_scalp_count,
                "protected_mode":     self.protected_mode,
                "risk_rules": [
                    f"Max {self.max_daily_scalps} scalps/session (protected mode)" if self.protected_mode else "No scalp count limit",
                    "Suspend scalping if DLL reaches 50%",
                    "Scalps count toward daily trade limit",
                    f"Hard stop: {stop_pts} pts — non-negotiable",
                    f"Max target: {target2_pts} pts — do NOT hold beyond T2",
                ],
                "confidence":    score,
                "confluence_factors": confluences,
            })

        except Exception as exc:
            logger.error("ScalpingStrategy error: %s", exc)

        return signals

    def is_session_valid_for_scalping(self, dt=None) -> bool:
        """Check if the current time is appropriate for scalping."""
        import datetime as _dt
        ts = dt or _dt.datetime.now(EASTERN)
        return _in_kill_zone(ts) and not _in_no_scalp_zone(ts)
