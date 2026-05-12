"""
P01 strategy: 15-minute ORB + break/retest logic.
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


def _to_eastern_dt(dt: datetime) -> datetime:
    """Normalize datetime to US/Eastern."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(EASTERN)


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with timezone-aware Eastern index."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class ORBStrategy:
    """15-minute ORB breakout/retest strategy with ICT/SMC filters."""

    def __init__(self) -> None:
        self.last_breakout_signal: Optional[str] = None

    def calculate_orb(self, bars_930_to_945: pd.DataFrame) -> dict:
        """Build opening range metrics from 9:30-9:45 ET one-minute bars."""
        try:
            logger.info("Calculating ORB window (9:30-9:45 ET)")
            if bars_930_to_945 is None or bars_930_to_945.empty:
                raise ValueError("bars_930_to_945 is empty")
            bars = _normalize_index(bars_930_to_945)
            for col in ("high", "low", "open", "close"):
                if col not in bars.columns:
                    raise ValueError(f"Missing column: {col}")

            window = bars.between_time("09:30", "09:45", inclusive="both")
            if window.empty:
                raise ValueError("No bars found in 9:30-9:45 ET window")

            orb_high = float(window["high"].max())
            orb_low = float(window["low"].min())
            orb_range = float(orb_high - orb_low)

            if orb_range < 2.0:
                quality = "NARROW"
            elif orb_range > 15.0:
                quality = "WIDE"
            else:
                quality = "NORMAL"

            return {
                "orb_high": orb_high,
                "orb_low": orb_low,
                "orb_range": orb_range,
                "range_quality": quality,
                "established": True,
                "extension_1x": orb_high + orb_range,
                "extension_2x": orb_high + (orb_range * 2.0),
                "extension_3x": orb_high + (orb_range * 3.0),
                "short_ext_1x": orb_low - orb_range,
                "short_ext_2x": orb_low - (orb_range * 2.0),
                "short_ext_3x": orb_low - (orb_range * 3.0),
            }
        except Exception as exc:
            logger.exception("calculate_orb failed: {}", exc)
            return {
                "orb_high": None,
                "orb_low": None,
                "orb_range": None,
                "range_quality": "NARROW",
                "established": False,
                "extension_1x": None,
                "extension_2x": None,
                "extension_3x": None,
                "short_ext_1x": None,
                "short_ext_2x": None,
                "short_ext_3x": None,
            }

    def _fvg_trap(self, context: dict, direction: str, orb_data: dict, tf: str = "5m") -> bool:
        """Return True if opposing FVG sits directly above/below ORB level."""
        fvgs = context.get("fvgs", {}).get(tf, {}).get("standard", [])
        orb_high = float(orb_data["orb_high"])
        orb_low = float(orb_data["orb_low"])
        proximity = max(float(orb_data["orb_range"]), 0.5)
        for f in fvgs:
            ftype = str(f.get("type", ""))
            top = float(f.get("top", 0.0))
            bottom = float(f.get("bottom", 0.0))
            if direction == "LONG" and ftype == "BEAR_FVG":
                if orb_high <= bottom <= orb_high + proximity:
                    return True
            if direction == "SHORT" and ftype == "BULL_FVG":
                if orb_low - proximity <= top <= orb_low:
                    return True
        return False

    def _volume_ok(self, current_bar: pd.Series, context: dict) -> bool:
        """Check if breakout volume is above average when volume data exists."""
        try:
            vol = float(current_bar.get("volume"))
            avg = float(context.get("volume_20bar_avg", 0.0))
            return vol > avg if avg > 0 else True
        except Exception:
            return True

    def _is_kill_window(self, ts: datetime) -> bool:
        """True during 9:30-10:30 ET for ORB peak window."""
        et = _to_eastern_dt(ts)
        return time(9, 30) <= et.time() <= time(10, 30)

    def _directional_open_bias(self, context: dict, direction: str) -> bool:
        """Infer first 15m directional bias from context hints."""
        opening_bias = str(context.get("opening_15m_bias", "NEUTRAL")).upper()
        return (direction == "LONG" and opening_bias in {"BULLISH", "UP"}) or (
            direction == "SHORT" and opening_bias in {"BEARISH", "DOWN"}
        )

    def _find_retest(
        self, direction: str, orb_data: dict, recent_bars: Optional[pd.DataFrame]
    ) -> Optional[Dict[str, Any]]:
        """Find first retest candle in last 6 bars."""
        if recent_bars is None or recent_bars.empty:
            return None
        bars = _normalize_index(recent_bars).tail(6)
        level = float(orb_data["orb_high"] if direction == "LONG" else orb_data["orb_low"])
        tol = 0.25
        for i in range(len(bars)):
            r = bars.iloc[i]
            l, h, o, c = float(r["low"]), float(r["high"]), float(r["open"]), float(r["close"])
            touch = l <= level + tol and h >= level - tol
            if direction == "LONG":
                valid = c >= level and l <= level + tol
            else:
                valid = c <= level and h >= level - tol
            if touch and valid:
                return {
                    "entry": c,
                    "entry_type": "RETEST",
                    "timestamp": bars.index[i].to_pydatetime(),
                    "rejection": (c >= o if direction == "LONG" else c <= o),
                }
        return None

    def check_breakout(self, current_bar, orb_data, context, instrument) -> dict | None:
        """Validate ORB breakout signal with HTF filters, FVG traps, and scoring."""
        try:
            if not orb_data or not orb_data.get("established"):
                return None
            row = current_bar if isinstance(current_bar, pd.Series) else pd.Series(current_bar)
            for col in ("open", "high", "low", "close"):
                if col not in row:
                    return None

            close = float(row["close"])
            orb_high = float(orb_data["orb_high"])
            orb_low = float(orb_data["orb_low"])
            direction = None
            if close > orb_high:
                direction = "LONG"
            elif close < orb_low:
                direction = "SHORT"
            if not direction:
                return None

            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
            if direction == "LONG" and not (h4 in {"BULLISH", "NEUTRAL"} and h1 in {"BULLISH", "NEUTRAL"}):
                return None
            if direction == "SHORT" and not (h4 in {"BEARISH", "NEUTRAL"} and h1 in {"BEARISH", "NEUTRAL"}):
                return None

            if self._fvg_trap(context, direction, orb_data, tf="5m"):
                return None

            if not self._volume_ok(row, context):
                return None

            recent_next = context.get("next_bar_preview")
            if isinstance(recent_next, dict):
                if direction == "LONG" and float(recent_next.get("close", close)) < orb_high:
                    return None
                if direction == "SHORT" and float(recent_next.get("close", close)) > orb_low:
                    return None

            recent_bars = context.get("recent_5m_bars")
            retest = self._find_retest(direction, orb_data, recent_bars)
            if retest:
                entry = float(retest["entry"])
                entry_type = "RETEST"
                signal_ts = retest["timestamp"]
            else:
                buffer_pts = 0.25
                entry = close + buffer_pts if direction == "LONG" else close - buffer_pts
                entry_type = "BREAKOUT"
                signal_ts = row.name.to_pydatetime() if hasattr(row.name, "to_pydatetime") else datetime.now(tz=EASTERN)

            stop = (orb_low - 0.5) if direction == "LONG" else (orb_high + 0.5)
            if direction == "LONG":
                t1, t2, t3 = orb_data["extension_1x"], orb_data["extension_2x"], orb_data["extension_3x"]
                strategy = "ORB_LONG"
                full_name = "15-Min Opening Range Breakout — Long"
            else:
                t1, t2, t3 = orb_data["short_ext_1x"], orb_data["short_ext_2x"], orb_data["short_ext_3x"]
                strategy = "ORB_SHORT"
                full_name = "15-Min Opening Range Breakout — Short"

            confluences: List[str] = []
            score = 0.55
            if (direction == "LONG" and h4 == "BULLISH") or (direction == "SHORT" and h4 == "BEARISH"):
                score += 0.10
                confluences.append("4H strong trend agreement")

            vwap_val = context.get("vwap_value")
            if vwap_val is not None:
                vwap_val = float(vwap_val)
                if (direction == "LONG" and entry > vwap_val) or (direction == "SHORT" and entry < vwap_val):
                    score += 0.08
                    confluences.append("VWAP aligned")
                if (direction == "LONG" and vwap_val > entry and vwap_val < t1) or (
                    direction == "SHORT" and vwap_val < entry and vwap_val > t1
                ):
                    score -= 0.08
                    confluences.append("VWAP_IN_WAY")

            supportive_fvg = False
            for f in context.get("fvgs", {}).get("5m", {}).get("standard", []):
                ftype = str(f.get("type"))
                if direction == "LONG" and ftype == "BULL_FVG":
                    supportive_fvg = True
                if direction == "SHORT" and ftype == "BEAR_FVG":
                    supportive_fvg = True
            if supportive_fvg:
                score += 0.08
                confluences.append("Directional FVG support")

            if self._directional_open_bias(context, direction):
                score += 0.07
                confluences.append("Opening directional bias")

            if orb_data.get("range_quality") == "NORMAL":
                score += 0.05
                confluences.append("Normal ORB range")

            ts_et = _to_eastern_dt(signal_ts)
            if self._is_kill_window(ts_et):
                score += 0.05
                confluences.append("ORB kill window timing")

            if bool(context.get("news_within_30m", False)):
                score -= 0.10
                confluences.append("News risk within 30m")

            opposes = (direction == "LONG" and h4 == "BEARISH") or (direction == "SHORT" and h4 == "BULLISH")
            if opposes:
                score -= 0.15
                confluences.append("Counter-trend breakout")

            score = max(0.0, min(1.0, score))
            self.last_breakout_signal = strategy
            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(t1),
                "target_2": float(t2),
                "target_3": float(t3),
                "orb_high": float(orb_high),
                "orb_low": float(orb_low),
                "orb_range": float(orb_data["orb_range"]),
                "range_quality": orb_data.get("range_quality", "NORMAL"),
                "entry_type": entry_type,
                "confidence": float(round(score, 2)),
                "confluence_factors": confluences,
                "description": f"{full_name}: {entry_type.lower()} entry at {entry:.2f}, ORB range {orb_data['orb_range']:.2f} pts.",
            }
        except Exception as exc:
            logger.exception("check_breakout failed: {}", exc)
            return None

    def check_failed_breakout(self, bars_since_breakout, orb_data) -> dict | None:
        """Detect 2-bar fakeout and return opposite-direction continuation setup."""
        try:
            if bars_since_breakout is None or len(bars_since_breakout) < 2:
                return None
            if not orb_data or not orb_data.get("established"):
                return None

            bars = _normalize_index(bars_since_breakout).tail(2)
            last_close = float(bars.iloc[-1]["close"])
            first_close = float(bars.iloc[0]["close"])
            orb_high = float(orb_data["orb_high"])
            orb_low = float(orb_data["orb_low"])

            broke_high_then_back = first_close > orb_high and last_close < orb_high
            broke_low_then_back = first_close < orb_low and last_close > orb_low

            if broke_high_then_back:
                entry = orb_low - 0.25
                stop = orb_high + 0.5
                return {
                    "strategy": "ORB_FAKEOUT_SHORT",
                    "strategy_full_name": "15-Min ORB Failed Breakout — Short",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(orb_data["short_ext_1x"]),
                    "target_2": float(orb_data["short_ext_2x"]),
                    "target_3": float(orb_data["short_ext_3x"]),
                    "confidence": 0.78,
                    "description": "Failed long breakout returned inside range; short continuation setup active.",
                }
            if broke_low_then_back:
                entry = orb_high + 0.25
                stop = orb_low - 0.5
                return {
                    "strategy": "ORB_FAKEOUT_LONG",
                    "strategy_full_name": "15-Min ORB Failed Breakout — Long",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(orb_data["extension_1x"]),
                    "target_2": float(orb_data["extension_2x"]),
                    "target_3": float(orb_data["extension_3x"]),
                    "confidence": 0.78,
                    "description": "Failed short breakout returned inside range; long continuation setup active.",
                }
            return None
        except Exception as exc:
            logger.exception("check_failed_breakout failed: {}", exc)
            return None

    def get_orb_status_string(self, orb_data, current_price) -> str:
        """Return readable ORB dashboard string."""
        try:
            if not orb_data or not orb_data.get("established"):
                return "ORB not set yet — waiting for 9:30-9:45 window."
            hi = float(orb_data["orb_high"])
            lo = float(orb_data["orb_low"])
            rng = float(orb_data["orb_range"])
            px = float(current_price)
            if px > hi:
                phase = f"Above ORB high ({hi:.2f}) — breakout watch."
            elif px < lo:
                phase = f"Below ORB low ({lo:.2f}) — breakdown watch."
            else:
                phase = "Inside ORB — waiting for decisive close."
            return f"ORB Set: H={hi:.2f} L={lo:.2f} Range={rng:.2f}pts | {phase}"
        except Exception:
            return "ORB status unavailable."
