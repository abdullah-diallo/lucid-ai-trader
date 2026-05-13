"""
P04 Strategy B: Fading exhausted rallies/drops.
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
    """Normalize DataFrame index to timezone-aware Eastern datetimes."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI series."""
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


class FadingStrategy:
    """Fade exhausted moves when momentum and context clearly deteriorate."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size
        self.minimum_signals_required = 3

    def _has_poi(self, price: float, context: dict) -> bool:
        """Require POI overlap (OB/FVG/key level) to allow fading."""
        for tf in ("5m", "15m"):
            for ob in context.get("order_blocks", {}).get(tf, {}).get("standard", []):
                if float(ob.get("low", price - 1)) <= price <= float(ob.get("high", price + 1)):
                    return True
            for f in context.get("fvgs", {}).get(tf, {}).get("standard", []):
                if float(f.get("bottom", price - 1)) <= price <= float(f.get("top", price + 1)):
                    return True
        for lvl in context.get("key_levels", []):
            if abs(float(lvl) - price) / max(abs(price), 1e-9) <= 0.001:
                return True
        return False

    def detect_exhaustion(self, df: pd.DataFrame, context: dict) -> dict | None:
        """Detect exhaustion setups requiring >=3 signals + POI context."""
        from analysis.utils import validate_dataframe
        if not validate_dataframe(df, min_bars=30, caller="strategy_fading.detect_exhaustion"):
            return None
        try:
            data = _normalize_df(df)
            for c in ("open", "high", "low", "close"):
                if c not in data.columns:
                    return None
            if len(data) < 30:
                return None

            last = data.iloc[-1]
            prev = data.iloc[-2]
            close = float(last["close"])
            open_ = float(last["open"])
            high = float(last["high"])
            low = float(last["low"])
            rng = max(high - low, 1e-9)
            body = abs(close - open_)
            upper_wick = (high - max(open_, close)) / rng
            lower_wick = (min(open_, close) - low) / rng

            rsi_val = float(_rsi(data["close"]).iloc[-1])
            pd_zone = str(context.get("premium_discount", {}).get("zone", "EQUILIBRIUM")).upper()
            vwap = context.get("vwap_value")
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()

            recent = data.tail(6)
            is_rally = float(recent["close"].iloc[-1]) > float(recent["close"].iloc[0])
            is_drop = float(recent["close"].iloc[-1]) < float(recent["close"].iloc[0])

            signals: List[str] = []
            fade_direction = None

            if "volume" in data.columns:
                vols = data["volume"].tail(5).tolist()
                if len(vols) >= 4 and vols[-1] < vols[-2] < vols[-3]:
                    signals.append("Decreasing volume")

            doji_like = body / rng <= 0.25
            if doji_like:
                signals.append("Doji/spinning top at extreme")

            if is_rally and pd_zone == "PREMIUM":
                signals.append("Premium zone overextension")
                fade_direction = "SHORT"
            if is_drop and pd_zone == "DISCOUNT":
                signals.append("Discount zone overextension")
                fade_direction = "LONG"

            if rsi_val > 75 and is_rally:
                signals.append("RSI overbought (>75)")
                fade_direction = "SHORT"
            if rsi_val < 25 and is_drop:
                signals.append("RSI oversold (<25)")
                fade_direction = "LONG"

            if is_rally:
                recent_high = float(data["high"].tail(3).max())
                prev_high = float(data["high"].tail(8).head(5).max())
                if recent_high <= prev_high:
                    signals.append("Failed new high (lower-high behavior)")
                    fade_direction = "SHORT"
            if is_drop:
                recent_low = float(data["low"].tail(3).min())
                prev_low = float(data["low"].tail(8).head(5).min())
                if recent_low >= prev_low:
                    signals.append("Failed new low (higher-low behavior)")
                    fade_direction = "LONG"

            if fade_direction is None:
                return None

            poi_price = high if fade_direction == "SHORT" else low
            if not self._has_poi(poi_price, context):
                return None

            if len(signals) < self.minimum_signals_required:
                return None

            # First reversal candle trigger.
            if fade_direction == "SHORT":
                reversal = close < open_ and upper_wick >= 0.35
                if not reversal:
                    return None
                entry = close
                stop = high + (2 * self.tick_size)
                target_1 = float(vwap) if vwap is not None else entry - 1.5 * (stop - entry)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
                target_2 = max([float(x["price"]) for x in swings if float(x["price"]) < entry], default=target_1)
                strategy = "FADE_SHORT"
                full_name = "Fading Exhausted Rally — Short"
            else:
                reversal = close > open_ and lower_wick >= 0.35
                if not reversal:
                    return None
                entry = close
                stop = low - (2 * self.tick_size)
                target_1 = float(vwap) if vwap is not None else entry + 1.5 * (entry - stop)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
                target_2 = min([float(x["price"]) for x in swings if float(x["price"]) > entry], default=target_1)
                strategy = "FADE_LONG"
                full_name = "Fading Oversold Drop — Long"

            confidence = 0.50 + min(0.25, (len(signals) - self.minimum_signals_required) * 0.06)
            if (strategy == "FADE_SHORT" and h4 == "BULLISH") or (strategy == "FADE_LONG" and h4 == "BEARISH"):
                confidence -= 0.10

            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(target_1),
                "target_2": float(target_2),
                "confidence": float(round(max(0.0, min(1.0, confidence)), 2)),
                "exhaustion_signals_count": int(len(signals)),
                "minimum_signals_required": int(self.minimum_signals_required),
                "exhaustion_signals": signals,
                "description": f"{full_name}: exhaustion confirmed with {len(signals)} signals at POI.",
            }
        except Exception as exc:
            logger.exception("detect_exhaustion failed: {}", exc)
            return None
