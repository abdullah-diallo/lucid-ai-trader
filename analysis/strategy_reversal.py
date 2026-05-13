"""
P10 Strategy A: Reversal and divergence trading.
"""

from __future__ import annotations

from typing import Any, Dict, List

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
    """Normalize index to timezone-aware US/Eastern datetime index."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI."""
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


class ReversalDivergenceStrategy:
    """Detect RSI/price divergence and structure-confirmed reversal entries."""

    def detect_divergence(self, df: pd.DataFrame, context: dict) -> list:
        """Detect bullish/bearish divergence at swing points with confluence metadata."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_reversal.detect_divergence"):
            return []
        try:
            data = _normalize_df(df)
            if len(data) < 40 or any(c not in data.columns for c in ("high", "low", "close")):
                return []

            rsi = _rsi(data["close"]).fillna(method="bfill")
            highs = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
            lows = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
            out: List[Dict[str, Any]] = []

            both_indices = bool(context.get("cross_index_divergence", False))
            choch_events = context.get("market_structure", {}).get("15m", {}).get("bos_choch", [])
            choch_bear = any("CHOCH_BEAR" == str(e.get("type")) for e in choch_events[-6:])
            choch_bull = any("CHOCH_BULL" == str(e.get("type")) for e in choch_events[-6:])

            # Bearish divergence: HH in price, LH in RSI.
            if len(highs) >= 2:
                p1, p2 = highs[-2], highs[-1]
                i1, i2 = int(p1["index"]), int(p2["index"])
                if i2 - i1 >= 5 and float(p2["price"]) > float(p1["price"]):
                    r1 = float(rsi.iloc[i1]) if i1 < len(rsi) else None
                    r2 = float(rsi.iloc[i2]) if i2 < len(rsi) else None
                    if r1 is not None and r2 is not None and (r1 - r2) >= 3.0:
                        rsi_diff = r1 - r2
                        strength = "STRONG" if both_indices and choch_bear else "MODERATE" if choch_bear else "WEAK"
                        out.append(
                            {
                                "type": "BEAR_DIV",
                                "timeframe": "5m",
                                "peak1_price": float(p1["price"]),
                                "peak1_rsi": r1,
                                "peak1_timestamp": p1["timestamp"],
                                "peak2_price": float(p2["price"]),
                                "peak2_rsi": r2,
                                "peak2_timestamp": p2["timestamp"],
                                "rsi_difference": float(round(rsi_diff, 2)),
                                "confirmed_by_choch": bool(choch_bear),
                                "both_indices": bool(both_indices),
                                "strength": strength,
                            }
                        )

            # Bullish divergence: LL in price, HL in RSI.
            if len(lows) >= 2:
                p1, p2 = lows[-2], lows[-1]
                i1, i2 = int(p1["index"]), int(p2["index"])
                if i2 - i1 >= 5 and float(p2["price"]) < float(p1["price"]):
                    r1 = float(rsi.iloc[i1]) if i1 < len(rsi) else None
                    r2 = float(rsi.iloc[i2]) if i2 < len(rsi) else None
                    if r1 is not None and r2 is not None and (r2 - r1) >= 3.0:
                        rsi_diff = r2 - r1
                        strength = "STRONG" if both_indices and choch_bull else "MODERATE" if choch_bull else "WEAK"
                        out.append(
                            {
                                "type": "BULL_DIV",
                                "timeframe": "5m",
                                "peak1_price": float(p1["price"]),
                                "peak1_rsi": r1,
                                "peak1_timestamp": p1["timestamp"],
                                "peak2_price": float(p2["price"]),
                                "peak2_rsi": r2,
                                "peak2_timestamp": p2["timestamp"],
                                "rsi_difference": float(round(rsi_diff, 2)),
                                "confirmed_by_choch": bool(choch_bull),
                                "both_indices": bool(both_indices),
                                "strength": strength,
                            }
                        )
            return out
        except Exception as exc:
            logger.exception("detect_divergence failed: {}", exc)
            return []

    def detect_reversal_entry(self, df, divergence: dict, context: dict) -> dict | None:
        """Generate reversal entry after CHoCH/MSS confirmation following divergence."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_reversal.detect_reversal_entry"):
            return None
        try:
            if not divergence:
                return None
            data = _normalize_df(df)
            if data.empty:
                return None

            div_type = divergence.get("type")
            ms15 = context.get("market_structure", {}).get("15m", {}).get("bos_choch", [])
            ms5 = context.get("market_structure", {}).get("5m", {}).get("bos_choch", [])

            if div_type == "BEAR_DIV":
                confirmed = any(e.get("type") in {"CHOCH_BEAR", "MSS_BEAR"} for e in (ms15[-6:] + ms5[-6:]))
                if not confirmed:
                    return None
                swing_lows = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
                if not swing_lows:
                    return None
                trigger = float(swing_lows[-1]["price"])
                last_close = float(data["close"].iloc[-1])
                if last_close > trigger:
                    return None
                entry = last_close
                stop = float(divergence["peak2_price"]) + 0.5
                vwap = context.get("vwap_value")
                t1 = float(vwap) if vwap and float(vwap) < entry else entry - 1.5 * (stop - entry)
                t2 = float(trigger)
                return {
                    "strategy": "REVERSAL_SHORT",
                    "strategy_full_name": "Reversal + Divergence Trade — Short at Trend Exhaustion",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(t1),
                    "target_2": float(t2),
                    "confidence": 0.66 if divergence.get("both_indices") else 0.58,
                    "description": "Bearish divergence confirmed by CHoCH/MSS; short reversal trigger active.",
                }

            if div_type == "BULL_DIV":
                confirmed = any(e.get("type") in {"CHOCH_BULL", "MSS_BULL"} for e in (ms15[-6:] + ms5[-6:]))
                if not confirmed:
                    return None
                swing_highs = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
                if not swing_highs:
                    return None
                trigger = float(swing_highs[-1]["price"])
                last_close = float(data["close"].iloc[-1])
                if last_close < trigger:
                    return None
                entry = last_close
                stop = float(divergence["peak2_price"]) - 0.5
                vwap = context.get("vwap_value")
                t1 = float(vwap) if vwap and float(vwap) > entry else entry + 1.5 * (entry - stop)
                t2 = float(trigger)
                return {
                    "strategy": "REVERSAL_LONG",
                    "strategy_full_name": "Reversal + Divergence Trade — Long at Trend Exhaustion",
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(t1),
                    "target_2": float(t2),
                    "confidence": 0.66 if divergence.get("both_indices") else 0.58,
                    "description": "Bullish divergence confirmed by CHoCH/MSS; long reversal trigger active.",
                }
            return None
        except Exception as exc:
            logger.exception("detect_reversal_entry failed: {}", exc)
            return None
