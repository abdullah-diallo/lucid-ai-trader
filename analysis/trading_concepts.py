"""
Shared ICT/SMC trading concepts foundation for lucid-ai-trader.

This module provides reusable analyzers for:
- market structure
- liquidity mapping
- fair value gaps (FVG / IFVG)
- order blocks / breaker blocks
- displacement candles
- sessions and kill zones
- VWAP utilities
- premium/discount zoning
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover - fallback when loguru not installed
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

EASTERN = pytz.timezone("US/Eastern")
UTC = pytz.utc


def _to_eastern(dt: datetime) -> datetime:
    """Normalize any datetime to US/Eastern timezone."""
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(EASTERN)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copied DataFrame with an Eastern timezone-aware DateTimeIndex."""
    local = df.copy()
    if not isinstance(local.index, pd.DatetimeIndex):
        local.index = pd.to_datetime(local.index)
    if local.index.tz is None:
        local.index = local.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        local.index = local.index.tz_convert(EASTERN)
    return local


def _required_columns(df: pd.DataFrame, cols: List[str]) -> None:
    """Validate required columns are present."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _safe_timestamp(df: pd.DataFrame, idx: int) -> datetime:
    """Return index timestamp at idx as Eastern datetime."""
    return _to_eastern(df.index[idx].to_pydatetime())


class MarketStructure:
    """Detects swing points, trend state, and structure breaks."""

    def detect_swing_points(self, df: pd.DataFrame, lookback: int = 5) -> dict:
        """Detect swing highs/lows where a bar exceeds both-side windows."""
        try:
            logger.info("Detecting swing points with lookback={}", lookback)
            data = _normalize_df(df)
            _required_columns(data, ["high", "low"])
            if len(data) < (lookback * 2 + 1):
                return {"swing_highs": [], "swing_lows": []}

            swing_highs: List[Dict[str, Any]] = []
            swing_lows: List[Dict[str, Any]] = []

            for i in range(lookback, len(data) - lookback):
                high = float(data["high"].iloc[i])
                low = float(data["low"].iloc[i])
                prev_highs = data["high"].iloc[i - lookback : i]
                next_highs = data["high"].iloc[i + 1 : i + 1 + lookback]
                prev_lows = data["low"].iloc[i - lookback : i]
                next_lows = data["low"].iloc[i + 1 : i + 1 + lookback]

                if high > float(prev_highs.max()) and high > float(next_highs.max()):
                    swing_highs.append(
                        {"price": high, "index": i, "timestamp": _safe_timestamp(data, i)}
                    )
                if low < float(prev_lows.min()) and low < float(next_lows.min()):
                    swing_lows.append(
                        {"price": low, "index": i, "timestamp": _safe_timestamp(data, i)}
                    )

            logger.info("Swing points found: highs={}, lows={}", len(swing_highs), len(swing_lows))
            return {"swing_highs": swing_highs, "swing_lows": swing_lows}
        except Exception as exc:
            logger.exception("detect_swing_points failed: {}", exc)
            return {"swing_highs": [], "swing_lows": []}

    def detect_trend(self, swing_highs: list, swing_lows: list) -> dict:
        """Classify trend by last two swing highs/lows into bullish, bearish, or ranging."""
        try:
            logger.info("Detecting trend from swing points")
            result = {
                "trend": "RANGING",
                "last_hh": None,
                "last_hl": None,
                "last_lh": None,
                "last_ll": None,
                "description": "Insufficient structure points; market appears ranging.",
            }

            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return result

            h1, h2 = swing_highs[-2], swing_highs[-1]
            l1, l2 = swing_lows[-2], swing_lows[-1]

            high_up = h2["price"] > h1["price"]
            low_up = l2["price"] > l1["price"]
            high_down = h2["price"] < h1["price"]
            low_down = l2["price"] < l1["price"]

            if high_up and low_up:
                result.update(
                    {
                        "trend": "BULLISH",
                        "last_hh": float(h2["price"]),
                        "last_hl": float(l2["price"]),
                        "description": "Bullish structure with higher highs and higher lows.",
                    }
                )
            elif high_down and low_down:
                result.update(
                    {
                        "trend": "BEARISH",
                        "last_lh": float(h2["price"]),
                        "last_ll": float(l2["price"]),
                        "description": "Bearish structure with lower highs and lower lows.",
                    }
                )
            else:
                result["description"] = "Mixed structure suggests a ranging market."

            return result
        except Exception as exc:
            logger.exception("detect_trend failed: {}", exc)
            return {
                "trend": "RANGING",
                "last_hh": None,
                "last_hl": None,
                "last_lh": None,
                "last_ll": None,
                "description": "Trend detection failed; defaulting to ranging.",
            }

    def detect_bos_choch(self, df: pd.DataFrame, swing_points: dict, trend: str) -> list:
        """Detect BOS, CHoCH and MSS events using closes beyond latest swing levels."""
        try:
            logger.info("Detecting BOS/CHoCH/MSS events in trend={}", trend)
            data = _normalize_df(df)
            _required_columns(data, ["close"])
            highs = swing_points.get("swing_highs", [])
            lows = swing_points.get("swing_lows", [])
            if not highs or not lows:
                return []

            latest_high = max(highs, key=lambda x: x["index"])
            latest_low = max(lows, key=lambda x: x["index"])
            bull_break_level = float(latest_high["price"])
            bear_break_level = float(latest_low["price"])

            events: List[Dict[str, Any]] = []
            choch_direction: Optional[str] = None
            choch_seen = False

            start_i = max(latest_high["index"], latest_low["index"]) + 1
            for i in range(start_i, len(data)):
                close = float(data["close"].iloc[i])
                ts = _safe_timestamp(data, i)
                event: Optional[Dict[str, Any]] = None

                if close > bull_break_level:
                    if trend == "BULLISH":
                        event = {
                            "type": "BOS_BULL",
                            "price_level": bull_break_level,
                            "timestamp": ts,
                            "candle_index": i,
                            "confirmed": True,
                            "description": "Bullish continuation: close broke above swing high.",
                        }
                    else:
                        etype = "CHOCH_BULL" if not choch_seen else "MSS_BULL"
                        event = {
                            "type": etype,
                            "price_level": bull_break_level,
                            "timestamp": ts,
                            "candle_index": i,
                            "confirmed": choch_seen,
                            "description": "Bullish structure break against prior trend; reversal developing.",
                        }
                        choch_direction = "BULL"
                        choch_seen = True
                    bull_break_level = close

                elif close < bear_break_level:
                    if trend == "BEARISH":
                        event = {
                            "type": "BOS_BEAR",
                            "price_level": bear_break_level,
                            "timestamp": ts,
                            "candle_index": i,
                            "confirmed": True,
                            "description": "Bearish continuation: close broke below swing low.",
                        }
                    else:
                        etype = "CHOCH_BEAR" if not choch_seen else "MSS_BEAR"
                        if choch_seen and choch_direction and choch_direction != "BEAR":
                            etype = "CHOCH_BEAR"
                        event = {
                            "type": etype,
                            "price_level": bear_break_level,
                            "timestamp": ts,
                            "candle_index": i,
                            "confirmed": choch_seen and etype.startswith("MSS"),
                            "description": "Bearish structure break against prior trend; reversal developing.",
                        }
                        choch_direction = "BEAR"
                        choch_seen = True
                    bear_break_level = close

                if event:
                    events.append(event)

            logger.info("Structure break events detected={}", len(events))
            return events
        except Exception as exc:
            logger.exception("detect_bos_choch failed: {}", exc)
            return []


class LiquidityAnalyzer:
    """Maps liquidity pools, session highs/lows, and stop-sweep events."""

    @staticmethod
    def _cluster_levels(levels: List[float], tolerance_pct: float = 0.001) -> List[Dict[str, Any]]:
        """Cluster levels within tolerance percent and return grouped averages."""
        clusters: List[List[float]] = []
        for lvl in sorted(levels):
            placed = False
            for cluster in clusters:
                ref = sum(cluster) / len(cluster)
                if abs(lvl - ref) / max(ref, 1e-9) <= tolerance_pct:
                    cluster.append(lvl)
                    placed = True
                    break
            if not placed:
                clusters.append([lvl])
        return [{"price": float(sum(c) / len(c)), "count": len(c)} for c in clusters if len(c) >= 2]

    def detect_liquidity_pools(self, df: pd.DataFrame, swing_points: dict) -> dict:
        """Detect BSL/SSL levels and equal highs/lows as strong liquidity clusters."""
        try:
            logger.info("Detecting liquidity pools")
            _ = _normalize_df(df)  # normalized for consistency and validation
            highs = [float(h["price"]) for h in swing_points.get("swing_highs", [])]
            lows = [float(l["price"]) for l in swing_points.get("swing_lows", [])]

            equal_highs = self._cluster_levels(highs, tolerance_pct=0.001)
            equal_lows = self._cluster_levels(lows, tolerance_pct=0.001)
            strong_high_prices = {round(x["price"], 6) for x in equal_highs}
            strong_low_prices = {round(x["price"], 6) for x in equal_lows}

            bsl_levels = [
                {
                    "price": p,
                    "strength": "STRONG" if round(p, 6) in strong_high_prices else "NORMAL",
                    "type": "BSL",
                }
                for p in highs
            ]
            ssl_levels = [
                {
                    "price": p,
                    "strength": "STRONG" if round(p, 6) in strong_low_prices else "NORMAL",
                    "type": "SSL",
                }
                for p in lows
            ]
            return {
                "bsl_levels": bsl_levels,
                "ssl_levels": ssl_levels,
                "equal_highs": equal_highs,
                "equal_lows": equal_lows,
            }
        except Exception as exc:
            logger.exception("detect_liquidity_pools failed: {}", exc)
            return {"bsl_levels": [], "ssl_levels": [], "equal_highs": [], "equal_lows": []}

    def detect_session_levels(self, df: pd.DataFrame, session: str) -> dict:
        """Return high/low of a requested session window as liquidity targets."""
        try:
            logger.info("Detecting session levels for {}", session)
            data = _normalize_df(df)
            _required_columns(data, ["high", "low"])
            session = session.upper().strip()

            windows = {
                "ASIA": ("20:00", "00:00"),
                "LONDON": ("02:00", "05:00"),
                "NY": ("07:00", "16:00"),
            }
            if session == "PREVIOUS_DAY":
                last_ts = data.index.max()
                prev_day = (last_ts - pd.Timedelta(days=1)).date()
                day_df = data[data.index.date == prev_day]
                if day_df.empty:
                    raise ValueError("No previous day data found")
                return {
                    "session_high": float(day_df["high"].max()),
                    "session_low": float(day_df["low"].min()),
                    "session": session,
                }

            if session not in windows:
                raise ValueError("Invalid session. Use ASIA | LONDON | NY | PREVIOUS_DAY")

            start, end = windows[session]
            if start < end:
                session_df = data.between_time(start, end, inclusive="left")
            else:
                part1 = data.between_time(start, "23:59:59")
                part2 = data.between_time("00:00", end, inclusive="left")
                session_df = pd.concat([part1, part2]).sort_index()

            if session_df.empty:
                raise ValueError(f"No bars found for session {session}")
            return {
                "session_high": float(session_df["high"].max()),
                "session_low": float(session_df["low"].min()),
                "session": session,
            }
        except Exception as exc:
            logger.exception("detect_session_levels failed: {}", exc)
            return {"session_high": None, "session_low": None, "session": session.upper() if session else "UNKNOWN"}

    def detect_liquidity_sweep(self, df: pd.DataFrame, liquidity_pools: dict) -> list:
        """Detect wick-through-and-close-back sweeps of BSL/SSL levels."""
        try:
            logger.info("Detecting liquidity sweeps")
            data = _normalize_df(df)
            _required_columns(data, ["high", "low", "close"])
            if len(data) < 2:
                return []

            diffs = data["close"].diff().abs()
            tick_size = float(diffs[diffs > 0].min()) if (diffs > 0).any() else 0.25
            threshold = tick_size * 2.0

            bsl = [float(x["price"]) for x in liquidity_pools.get("bsl_levels", [])]
            ssl = [float(x["price"]) for x in liquidity_pools.get("ssl_levels", [])]
            sweeps: List[Dict[str, Any]] = []

            for i in range(0, len(data) - 1):
                row = data.iloc[i]
                nxt = data.iloc[i + 1]
                ts = _safe_timestamp(data, i)

                for lvl in bsl:
                    if float(row["high"]) >= lvl + threshold and float(row["close"]) < lvl:
                        sweeps.append(
                            {
                                "type": "BSL_SWEEP",
                                "swept_level": lvl,
                                "sweep_high": float(row["high"]),
                                "close_price": float(row["close"]),
                                "timestamp": ts,
                                "reversal_signal": float(nxt["close"]) < float(row["close"]),
                            }
                        )
                for lvl in ssl:
                    if float(row["low"]) <= lvl - threshold and float(row["close"]) > lvl:
                        sweeps.append(
                            {
                                "type": "SSL_SWEEP",
                                "swept_level": lvl,
                                "sweep_high": float(row["low"]),
                                "close_price": float(row["close"]),
                                "timestamp": ts,
                                "reversal_signal": float(nxt["close"]) > float(row["close"]),
                            }
                        )
            logger.info("Liquidity sweeps detected={}", len(sweeps))
            return sweeps
        except Exception as exc:
            logger.exception("detect_liquidity_sweep failed: {}", exc)
            return []


class FVGAnalyzer:
    """Detects fair value gaps and inverse fair value gaps."""

    def detect_fvgs(self, df: pd.DataFrame, timeframe: str,
                    instrument: str = "MES") -> list:
        """Find bullish/bearish 3-candle imbalances and fill status."""
        try:
            from analysis.utils import get_min_fvg_size
            logger.info("Detecting FVGs for timeframe={}", timeframe)
            data = _normalize_df(df)
            _required_columns(data, ["high", "low", "close", "open"])
            if len(data) < 3:
                return []

            min_size = get_min_fvg_size(instrument)
            fvgs: List[Dict[str, Any]] = []
            for i in range(1, len(data) - 1):
                prev_row = data.iloc[i - 1]
                middle   = data.iloc[i]
                next_row = data.iloc[i + 1]
                ts = _safe_timestamp(data, i)
                future = data.iloc[i + 1 :]

                # Displacement body filter — middle candle body must be >60% of range
                body = abs(float(middle["close"]) - float(middle["open"]))
                candle_range = float(middle["high"]) - float(middle["low"])
                if candle_range > 0 and body / candle_range < 0.60:
                    continue

                if float(next_row["low"]) > float(prev_row["high"]):
                    top = float(next_row["low"])
                    bottom = float(prev_row["high"])
                    if top - bottom < min_size:
                        continue
                    midpoint = (top + bottom) / 2.0
                    filled = bool((future["close"] <= midpoint).any())
                    partial = bool((future["low"] <= top).any()) and not filled
                    fvgs.append(
                        {
                            "type": "BULL_FVG",
                            "top": top,
                            "bottom": bottom,
                            "midpoint": midpoint,
                            "timeframe": timeframe,
                            "timestamp": ts,
                            "filled": filled,
                            "partially_filled": partial,
                            "age_bars": len(data) - i - 1,
                            "size_points": top - bottom,
                        }
                    )

                if float(next_row["high"]) < float(prev_row["low"]):
                    top = float(prev_row["low"])
                    bottom = float(next_row["high"])
                    if top - bottom < min_size:
                        continue
                    midpoint = (top + bottom) / 2.0
                    filled = bool((future["close"] >= midpoint).any())
                    partial = bool((future["high"] >= bottom).any()) and not filled
                    fvgs.append(
                        {
                            "type": "BEAR_FVG",
                            "top": top,
                            "bottom": bottom,
                            "midpoint": midpoint,
                            "timeframe": timeframe,
                            "timestamp": ts,
                            "filled": filled,
                            "partially_filled": partial,
                            "age_bars": len(data) - i - 1,
                            "size_points": top - bottom,
                        }
                    )
            return fvgs
        except Exception as exc:
            logger.exception("detect_fvgs failed: {}", exc)
            return []

    def detect_ifvgs(self, df: pd.DataFrame, filled_fvgs: list) -> list:
        """Convert filled FVGs into inverse role zones when rejection is observed."""
        try:
            logger.info("Detecting IFVGs from filled FVGs")
            data = _normalize_df(df)
            _required_columns(data, ["high", "low", "close"])
            ifvgs: List[Dict[str, Any]] = []

            for fvg in filled_fvgs:
                if not fvg.get("filled", False):
                    continue
                f_ts = fvg.get("timestamp")
                if isinstance(f_ts, datetime):
                    f_ts = _to_eastern(f_ts)
                subset = data[data.index >= pd.Timestamp(f_ts)] if f_ts else data
                if subset.empty:
                    continue

                if fvg["type"] == "BULL_FVG":
                    reject = bool((subset["high"] >= float(fvg["top"])).any() and (subset["close"] < float(fvg["midpoint"])).any())
                    if reject:
                        inverse = dict(fvg)
                        inverse["type"] = "BEAR_FVG"
                        inverse["is_inverse"] = True
                        ifvgs.append(inverse)
                elif fvg["type"] == "BEAR_FVG":
                    reject = bool((subset["low"] <= float(fvg["bottom"])).any() and (subset["close"] > float(fvg["midpoint"])).any())
                    if reject:
                        inverse = dict(fvg)
                        inverse["type"] = "BULL_FVG"
                        inverse["is_inverse"] = True
                        ifvgs.append(inverse)
            return ifvgs
        except Exception as exc:
            logger.exception("detect_ifvgs failed: {}", exc)
            return []


class OrderBlockAnalyzer:
    """Detects order blocks and breaker blocks around BOS events."""

    @staticmethod
    def find_ob_candle(data: "pd.DataFrame", bos_index: int, direction: str) -> int:
        """Scan backwards from bos_index (max 8 bars) for the last opposite-color candle."""
        max_lookback = min(8, bos_index)
        for i in range(bos_index - 1, bos_index - max_lookback - 1, -1):
            candle = data.iloc[i]
            is_bearish = float(candle["close"]) < float(candle["open"])
            is_bullish = float(candle["close"]) > float(candle["open"])
            if direction == "BULL" and is_bearish:
                return i
            if direction == "BEAR" and is_bullish:
                return i
        return -1

    def detect_order_blocks(self, df: pd.DataFrame, bos_events: list) -> list:
        """Find last opposing candle before BOS impulse and evaluate mitigation."""
        try:
            logger.info("Detecting order blocks from BOS events")
            data = _normalize_df(df)
            _required_columns(data, ["open", "high", "low", "close"])
            obs: List[Dict[str, Any]] = []
            if not bos_events:
                return obs

            for ev in bos_events:
                et = ev.get("type", "")
                idx = int(ev.get("candle_index", -1))
                if idx <= 0 or idx >= len(data):
                    continue

                if et in {"BOS_BULL", "MSS_BULL", "CHOCH_BULL"}:
                    ob_idx = self.find_ob_candle(data, idx, "BULL")
                    ob_type = "BULL_OB"
                elif et in {"BOS_BEAR", "MSS_BEAR", "CHOCH_BEAR"}:
                    ob_idx = self.find_ob_candle(data, idx, "BEAR")
                    ob_type = "BEAR_OB"
                else:
                    continue

                if ob_idx < 0:
                    continue

                high = float(data["high"].iloc[ob_idx])
                low = float(data["low"].iloc[ob_idx])
                midpoint = (high + low) / 2.0
                impulse_close = float(data["close"].iloc[idx])
                displacement = abs(impulse_close - midpoint)
                candle_count_from_bos = idx - ob_idx
                future = data.iloc[idx + 1 :]
                if ob_type == "BULL_OB":
                    mitigated = bool((future["low"] < low).any()) if not future.empty else False
                else:
                    mitigated = bool((future["high"] > high).any()) if not future.empty else False

                # OBs more than 6 bars from BOS are inherently weak
                if candle_count_from_bos > 6:
                    strength = "WEAK"
                elif displacement > 2.0 * max(high - low, 1e-9):
                    strength = "STRONG"
                elif displacement > 1.0 * max(high - low, 1e-9):
                    strength = "MEDIUM"
                else:
                    strength = "WEAK"

                obs.append(
                    {
                        "type": ob_type,
                        "high": high,
                        "low": low,
                        "midpoint": midpoint,
                        "timestamp": _safe_timestamp(data, ob_idx),
                        "mitigated": mitigated,
                        "strength": strength,
                        "displacement_size": displacement,
                        "candle_count_from_bos": candle_count_from_bos,
                    }
                )
            logger.info("Order blocks detected={}", len(obs))
            return obs
        except Exception as exc:
            logger.exception("detect_order_blocks failed: {}", exc)
            return []

    def detect_breaker_blocks(self, order_blocks: list, df: pd.DataFrame) -> list:
        """Flip mitigated order blocks into breaker blocks."""
        try:
            logger.info("Detecting breaker blocks")
            _ = _normalize_df(df)
            breakers: List[Dict[str, Any]] = []
            for ob in order_blocks:
                if not ob.get("mitigated"):
                    continue
                b = dict(ob)
                b["is_breaker"] = True
                b["type"] = "BEAR_OB" if ob.get("type") == "BULL_OB" else "BULL_OB"
                breakers.append(b)
            return breakers
        except Exception as exc:
            logger.exception("detect_breaker_blocks failed: {}", exc)
            return []


class DisplacementDetector:
    """Detect large aggressive candles likely showing institutional intent."""

    def detect_displacement(self, df: pd.DataFrame) -> list:
        """Detect candles with large body and size > 1.5x 20-bar average range."""
        try:
            logger.info("Detecting displacement candles")
            data = _normalize_df(df)
            _required_columns(data, ["open", "high", "low", "close"])
            if len(data) < 21:
                return []

            ranges = (data["high"] - data["low"]).abs()
            avg20 = ranges.rolling(20).mean()
            events: List[Dict[str, Any]] = []

            for i in range(20, len(data)):
                o = float(data["open"].iloc[i])
                h = float(data["high"].iloc[i])
                l = float(data["low"].iloc[i])
                c = float(data["close"].iloc[i])
                rng = max(h - l, 1e-9)
                body = abs(c - o)
                body_pct = body / rng
                size_mult = rng / max(float(avg20.iloc[i]), 1e-9)

                if body_pct <= 0.70 or size_mult <= 1.5:
                    continue

                creates_fvg = False
                if 1 <= i < len(data) - 1:
                    prev_h = float(data["high"].iloc[i - 1])
                    prev_l = float(data["low"].iloc[i - 1])
                    nxt_h = float(data["high"].iloc[i + 1])
                    nxt_l = float(data["low"].iloc[i + 1])
                    creates_fvg = bool(nxt_l > prev_h or nxt_h < prev_l)

                events.append(
                    {
                        "direction": "BULL" if c > o else "BEAR",
                        "body_percent": body_pct,
                        "size_multiplier": size_mult,
                        "timestamp": _safe_timestamp(data, i),
                        "creates_fvg": creates_fvg,
                    }
                )
            return events
        except Exception as exc:
            logger.exception("detect_displacement failed: {}", exc)
            return []


class SessionManager:
    """Session utilities aligned to ICT timing and kill-zone logic."""

    SESSION_TIMES = {
        "ASIA": {"open": "20:00", "close": "00:00"},
        "LONDON": {"open": "02:00", "close": "05:00"},
        "NY_OPEN": {"open": "07:00", "close": "10:00"},
        "NY_AM": {"open": "09:30", "close": "12:00"},
        "OVERLAP": {"open": "08:00", "close": "12:00"},
        "NY_LUNCH": {"open": "12:00", "close": "14:00"},
        "NY_PM": {"open": "14:00", "close": "16:00"},
        "AFTER_HOURS": {"open": "16:00", "close": "20:00"},
    }

    @staticmethod
    def _to_time(s: str) -> time:
        """Parse HH:MM time string."""
        hh, mm = s.split(":")
        return time(int(hh), int(mm))

    def _in_window(self, dt: datetime, start: time, end: time) -> bool:
        """Check if time is inside a session window, handling midnight-cross sessions."""
        t = _to_eastern(dt).time()
        if start <= end:
            return start <= t < end
        return t >= start or t < end

    def get_current_session(self, dt: datetime) -> str:
        """Return active session name for supplied datetime."""
        try:
            et = _to_eastern(dt)
            for name, win in self.SESSION_TIMES.items():
                if self._in_window(et, self._to_time(win["open"]), self._to_time(win["close"])):
                    return name
            return "OUT_OF_SESSION"
        except Exception as exc:
            logger.exception("get_current_session failed: {}", exc)
            return "OUT_OF_SESSION"

    def is_kill_zone(self, dt: datetime) -> bool:
        """True during London (2-5 ET) or NY Open (7-10 ET) kill zones."""
        try:
            et = _to_eastern(dt)
            london = self._in_window(et, time(2, 0), time(5, 0))
            ny_open = self._in_window(et, time(7, 0), time(10, 0))
            return london or ny_open
        except Exception as exc:
            logger.exception("is_kill_zone failed: {}", exc)
            return False

    def is_dead_zone(self, dt: datetime) -> bool:
        """True during NY lunch dead zone from 12:00-14:00 ET."""
        try:
            return self._in_window(_to_eastern(dt), time(12, 0), time(14, 0))
        except Exception as exc:
            logger.exception("is_dead_zone failed: {}", exc)
            return False

    def get_session_bias(self, session: str) -> str:
        """Return expected behavioral bias for each named session."""
        try:
            mapping = {
                "ASIA": "ACCUMULATION",
                "LONDON": "MANIPULATION",
                "NY_OPEN": "DISTRIBUTION",
                "OVERLAP": "HIGH_VOLATILITY",
            }
            return mapping.get(session.upper(), "NEUTRAL")
        except Exception as exc:
            logger.exception("get_session_bias failed: {}", exc)
            return "NEUTRAL"

    def get_orb_window(self, dt: datetime) -> bool:
        """Return True only between 9:30 and 9:45 ET."""
        try:
            et = _to_eastern(dt)
            return self._in_window(et, time(9, 30), time(9, 45))
        except Exception as exc:
            logger.exception("get_orb_window failed: {}", exc)
            return False


class VWAPCalculator:
    """VWAP and anchored VWAP utilities."""

    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Compute day-reset VWAP from 9:30 ET onward for each trading day."""
        try:
            logger.info("Calculating session VWAP")
            data = _normalize_df(df)
            _required_columns(data, ["high", "low", "close", "volume"])
            typical = (data["high"] + data["low"] + data["close"]) / 3.0
            trade_date = data.index.date
            after_open = data.index.time >= time(9, 30)

            vwap = pd.Series(index=data.index, dtype=float)
            for d in sorted(set(trade_date)):
                mask = (trade_date == d) & after_open
                if not mask.any():
                    continue
                tpv = (typical[mask] * data.loc[mask, "volume"]).cumsum()
                cum_vol = data.loc[mask, "volume"].cumsum().replace(0, pd.NA)
                vwap.loc[mask] = tpv / cum_vol
            return vwap
        except Exception as exc:
            logger.exception("calculate_vwap failed: {}", exc)
            return pd.Series(index=df.index, dtype=float)

    def get_vwap_position(self, current_price: float, vwap: float) -> dict:
        """Describe relative location and bias versus VWAP."""
        try:
            if vwap is None or pd.isna(vwap):
                raise ValueError("VWAP is unavailable")
            dist_points = float(current_price - vwap)
            dist_pct = (dist_points / max(abs(vwap), 1e-9)) * 100.0
            at = abs(dist_pct) <= 0.1
            if at:
                position, bias = "AT", "NEUTRAL"
            elif dist_points > 0:
                position, bias = "ABOVE", "BULLISH"
            else:
                position, bias = "BELOW", "BEARISH"
            return {
                "position": position,
                "distance_points": dist_points,
                "distance_percent": dist_pct,
                "bias": bias,
                "description": f"Price is {abs(dist_points):.2f} points {position.lower()} VWAP — {bias.lower()} intraday bias.",
            }
        except Exception as exc:
            logger.exception("get_vwap_position failed: {}", exc)
            return {
                "position": "AT",
                "distance_points": 0.0,
                "distance_percent": 0.0,
                "bias": "NEUTRAL",
                "description": "VWAP position unavailable.",
            }

    def calculate_anchored_vwap(self, df: pd.DataFrame, anchor_index: int) -> pd.Series:
        """Compute anchored VWAP beginning at a specific bar index."""
        try:
            logger.info("Calculating anchored VWAP from index={}", anchor_index)
            data = _normalize_df(df)
            _required_columns(data, ["high", "low", "close", "volume"])
            if anchor_index < 0 or anchor_index >= len(data):
                raise ValueError("anchor_index out of range")
            typical = (data["high"] + data["low"] + data["close"]) / 3.0
            out = pd.Series(index=data.index, dtype=float)
            sl = data.iloc[anchor_index:]
            tpv = (typical.iloc[anchor_index:] * sl["volume"]).cumsum()
            cum_vol = sl["volume"].cumsum().replace(0, pd.NA)
            out.iloc[anchor_index:] = tpv / cum_vol
            return out
        except Exception as exc:
            logger.exception("calculate_anchored_vwap failed: {}", exc)
            return pd.Series(index=df.index, dtype=float)


def get_premium_discount(current_price, swing_high, swing_low) -> dict:
    """Classify current price as premium/discount/equilibrium within swing range."""
    try:
        high = float(swing_high)
        low = float(swing_low)
        if high <= low:
            raise ValueError("swing_high must be greater than swing_low")

        eq = (high + low) / 2.0
        perc = ((float(current_price) - low) / (high - low)) * 100.0
        perc = max(0.0, min(100.0, perc))

        if abs(float(current_price) - eq) / max(eq, 1e-9) <= 0.001:
            zone = "EQUILIBRIUM"
            rec = "NEUTRAL"
        elif current_price > eq:
            zone = "PREMIUM"
            rec = "LOOK_FOR_SHORTS"
        else:
            zone = "DISCOUNT"
            rec = "LOOK_FOR_LONGS"

        ote = low + 0.618 * (high - low) if zone != "PREMIUM" else high - 0.618 * (high - low)
        return {
            "zone": zone,
            "eq_level": eq,
            "ote_level": ote,
            "percent_in_range": perc,
            "recommendation": rec,
        }
    except Exception as exc:
        logger.exception("get_premium_discount failed: {}", exc)
        return {
            "zone": "EQUILIBRIUM",
            "eq_level": None,
            "ote_level": None,
            "percent_in_range": 50.0,
            "recommendation": "NEUTRAL",
        }


def _overall_bias(ms_by_tf: Dict[str, Dict[str, Any]]) -> str:
    """Compute majority bias from per-timeframe market structure trends."""
    votes = {"BULLISH": 0, "BEARISH": 0, "RANGING": 0}
    for tf_data in ms_by_tf.values():
        tr = tf_data.get("trend", "RANGING")
        votes[tr] = votes.get(tr, 0) + 1
    return max(votes, key=votes.get)


def _extract_key_levels(context: Dict[str, Any], limit: int = 5) -> List[float]:
    """Extract top unique price levels from context to use as key levels."""
    levels: List[float] = []
    for tf, data in context.get("liquidity_pools", {}).items():
        for item in data.get("bsl_levels", []) + data.get("ssl_levels", []):
            levels.append(float(item["price"]))
    for tf, data in context.get("order_blocks", {}).items():
        for item in data.get("standard", []):
            levels.extend([float(item["high"]), float(item["low"]), float(item["midpoint"])])
    unique = sorted({round(x, 6) for x in levels})
    return unique[:limit]


def build_full_context(df_dict: dict, current_dt: datetime) -> dict:
    """Run full cross-timeframe analysis and return a master context dictionary."""
    try:
        logger.info("Building full context for all timeframes")
        required_tfs = {"1D", "4H", "1H", "15m", "5m", "1m"}
        missing = required_tfs - set(df_dict.keys())
        if missing:
            raise ValueError(f"Missing timeframe data: {sorted(missing)}")

        ms = MarketStructure()
        la = LiquidityAnalyzer()
        fvg = FVGAnalyzer()
        oba = OrderBlockAnalyzer()
        dd = DisplacementDetector()
        sm = SessionManager()
        vw = VWAPCalculator()

        market_structure: Dict[str, Dict[str, Any]] = {}
        liquidity: Dict[str, Dict[str, Any]] = {}
        fvg_out: Dict[str, Dict[str, Any]] = {}
        order_blocks: Dict[str, Dict[str, Any]] = {}
        displacements: Dict[str, List[Dict[str, Any]]] = {}
        liquidity_sweeps: Dict[str, List[Dict[str, Any]]] = {}
        bos_by_tf: Dict[str, List[Dict[str, Any]]] = {}

        for tf, raw_df in df_dict.items():
            data = _normalize_df(raw_df)
            swings = ms.detect_swing_points(data, lookback=5)
            trend_info = ms.detect_trend(swings["swing_highs"], swings["swing_lows"])
            bos_events = ms.detect_bos_choch(data, swings, trend_info["trend"])
            market_structure[tf] = {"swings": swings, **trend_info, "bos_choch": bos_events}
            bos_by_tf[tf] = bos_events

            lp = la.detect_liquidity_pools(data, swings)
            liquidity[tf] = lp
            liquidity_sweeps[tf] = la.detect_liquidity_sweep(data, lp)

            fvgs = fvg.detect_fvgs(data, tf)
            ifvgs = fvg.detect_ifvgs(data, [x for x in fvgs if x.get("filled")])
            fvg_out[tf] = {"standard": fvgs, "inverse": ifvgs}

            obs = oba.detect_order_blocks(data, bos_events)
            breakers = oba.detect_breaker_blocks(obs, data)
            order_blocks[tf] = {"standard": obs, "breakers": breakers}

            displacements[tf] = dd.detect_displacement(data)

        current_price = float(df_dict["1m"]["close"].iloc[-1])
        vwap_series = vw.calculate_vwap(df_dict["1m"])
        vwap_value = float(vwap_series.dropna().iloc[-1]) if not vwap_series.dropna().empty else None
        vwap_position = vw.get_vwap_position(current_price=current_price, vwap=vwap_value) if vwap_value else {
            "position": "AT",
            "distance_points": 0.0,
            "distance_percent": 0.0,
            "bias": "NEUTRAL",
            "description": "VWAP unavailable.",
        }

        one_hour_swings = market_structure["1H"]["swings"]
        if one_hour_swings["swing_highs"] and one_hour_swings["swing_lows"]:
            swing_high = float(one_hour_swings["swing_highs"][-1]["price"])
            swing_low = float(one_hour_swings["swing_lows"][-1]["price"])
        else:
            swing_high = float(df_dict["1H"]["high"].tail(50).max())
            swing_low = float(df_dict["1H"]["low"].tail(50).min())
        premium_discount = get_premium_discount(current_price, swing_high, swing_low)

        session_name = sm.get_current_session(current_dt)
        key_levels = _extract_key_levels({"liquidity_pools": liquidity, "order_blocks": order_blocks})
        nearest_poi = min(key_levels, key=lambda x: abs(x - current_price)) if key_levels else None

        context = {
            "market_structure": market_structure,
            "liquidity_pools": liquidity,
            "liquidity_sweeps": liquidity_sweeps,
            "fvgs": fvg_out,
            "order_blocks": order_blocks,
            "displacement": displacements,
            "current_session": session_name,
            "is_kill_zone": sm.is_kill_zone(current_dt),
            "vwap_position": vwap_position,
            "premium_discount": premium_discount,
            "overall_bias": _overall_bias({k: v for k, v in market_structure.items()}),
            "key_levels": key_levels,
            "nearest_poi": nearest_poi,
            "current_price": current_price,
            "generated_at": _to_eastern(current_dt),
        }
        logger.info("Full context built successfully")
        return context
    except Exception as exc:
        logger.exception("build_full_context failed: {}", exc)
        return {
            "market_structure": {},
            "liquidity_pools": {},
            "liquidity_sweeps": {},
            "fvgs": {},
            "order_blocks": {},
            "displacement": {},
            "current_session": "OUT_OF_SESSION",
            "is_kill_zone": False,
            "vwap_position": {
                "position": "AT",
                "distance_points": 0.0,
                "distance_percent": 0.0,
                "bias": "NEUTRAL",
                "description": "Unavailable due to error.",
            },
            "premium_discount": {
                "zone": "EQUILIBRIUM",
                "eq_level": None,
                "ote_level": None,
                "percent_in_range": 50.0,
                "recommendation": "NEUTRAL",
            },
            "overall_bias": "RANGING",
            "key_levels": [],
            "nearest_poi": None,
            "current_price": None,
            "generated_at": _to_eastern(current_dt),
        }


@dataclass
class TradingConceptsEngine:
    """Facade exposing one clean interface for all trading concept analyzers."""

    market_structure: MarketStructure = MarketStructure()
    liquidity: LiquidityAnalyzer = LiquidityAnalyzer()
    fvg: FVGAnalyzer = FVGAnalyzer()
    order_blocks: OrderBlockAnalyzer = OrderBlockAnalyzer()
    displacement: DisplacementDetector = DisplacementDetector()
    session: SessionManager = SessionManager()
    vwap: VWAPCalculator = VWAPCalculator()

    def build_context(self, df_dict: dict, current_dt: datetime) -> dict:
        """Build complete multi-timeframe context for strategy and analyst modules."""
        try:
            return build_full_context(df_dict, current_dt)
        except Exception as exc:
            logger.exception("TradingConceptsEngine.build_context failed: {}", exc)
            return {}


if __name__ == "__main__":
    try:
        logger.info("Running trading_concepts.py self-test block")
        idx = pd.date_range(
            start="2026-05-01 00:00:00",
            periods=500,
            freq="5min",
            tz="UTC",
        )
        base = pd.Series(range(len(idx)), index=idx, dtype=float)
        sample = pd.DataFrame(
            {
                "open": 5000 + (base * 0.05) + (base % 7) * 0.2,
                "high": 5001 + (base * 0.05) + (base % 11) * 0.25,
                "low": 4999 + (base * 0.05) - (base % 9) * 0.22,
                "close": 5000 + (base * 0.05) + ((base % 5) - 2) * 0.18,
                "volume": 1000 + (base % 20) * 25,
            },
            index=idx,
        )

        engine = TradingConceptsEngine()
        ms = engine.market_structure.detect_swing_points(sample)
        tr = engine.market_structure.detect_trend(ms["swing_highs"], ms["swing_lows"])
        bos = engine.market_structure.detect_bos_choch(sample, ms, tr["trend"])
        lp = engine.liquidity.detect_liquidity_pools(sample, ms)
        sl = engine.liquidity.detect_session_levels(sample, "NY")
        sweeps = engine.liquidity.detect_liquidity_sweep(sample, lp)
        fvgs = engine.fvg.detect_fvgs(sample, "5m")
        ifvgs = engine.fvg.detect_ifvgs(sample, [x for x in fvgs if x["filled"]])
        obs = engine.order_blocks.detect_order_blocks(sample, bos)
        breakers = engine.order_blocks.detect_breaker_blocks(obs, sample)
        disp = engine.displacement.detect_displacement(sample)
        now_et = datetime.now(EASTERN)
        session = engine.session.get_current_session(now_et)
        kill_zone = engine.session.is_kill_zone(now_et)
        dead_zone = engine.session.is_dead_zone(now_et)
        orb_window = engine.session.get_orb_window(now_et)
        vwap_series = engine.vwap.calculate_vwap(sample)
        vwap_last = float(vwap_series.dropna().iloc[-1]) if not vwap_series.dropna().empty else float(sample["close"].iloc[-1])
        vpos = engine.vwap.get_vwap_position(float(sample["close"].iloc[-1]), vwap_last)
        avwap = engine.vwap.calculate_anchored_vwap(sample, anchor_index=50)
        prem = get_premium_discount(float(sample["close"].iloc[-1]), float(sample["high"].max()), float(sample["low"].min()))

        df_dict = {
            "1D": sample.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(),
            "4H": sample.resample("4H").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(),
            "1H": sample.resample("1H").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(),
            "15m": sample.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(),
            "5m": sample.copy(),
            "1m": sample.resample("1min").ffill().dropna(),
        }
        full = engine.build_context(df_dict, datetime.now(tz=UTC))

        print("Self-test complete:")
        print("swings:", len(ms["swing_highs"]), len(ms["swing_lows"]))
        print("trend:", tr["trend"], "| bos events:", len(bos))
        print("liquidity pools:", len(lp["bsl_levels"]), len(lp["ssl_levels"]), "| sweeps:", len(sweeps))
        print("fvgs:", len(fvgs), "| ifvgs:", len(ifvgs))
        print("obs:", len(obs), "| breakers:", len(breakers))
        print("displacement:", len(disp))
        print("session:", session, "| kill_zone:", kill_zone, "| dead_zone:", dead_zone, "| orb_window:", orb_window)
        print("vwap pos:", vpos["position"], "| anchored vwap points:", avwap.dropna().shape[0])
        print("premium zone:", prem["zone"])
        print("full context keys:", list(full.keys()))
    except Exception as self_test_exc:
        logger.exception("Self-test block failed: {}", self_test_exc)
