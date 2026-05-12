"""
P02 Strategy B: Mean Reversion to VWAP.
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
    """Normalize index to timezone-aware Eastern datetime index."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class MeanReversionStrategy:
    """Trades VWAP snapback only in verified ranging market conditions."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def is_ranging_market(self, context: dict) -> bool:
        """Return True only when all strict ranging filters pass."""
        try:
            h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            vwap_touches = int(context.get("vwap_touch_count_today", 0))
            atr_15m = float(context.get("atr_15m_14", 0.0))
            atr_20d = float(context.get("atr_15m_20d_avg", 0.0))

            cond1 = h1 == "RANGING"
            cond2 = h4 not in {"BULLISH", "BEARISH"}
            cond3 = vwap_touches >= 2
            cond4 = atr_20d > 0 and atr_15m < atr_20d
            return bool(cond1 and cond2 and cond3 and cond4)
        except Exception as exc:
            logger.exception("is_ranging_market failed: {}", exc)
            return False

    def detect_mean_reversion(self, df: pd.DataFrame, context: dict) -> list:
        """Detect overextension from VWAP and trigger reversal entries back to mean."""
        try:
            if not self.is_ranging_market(context):
                return []

            data = _normalize_df(df)
            for col in ("open", "high", "low", "close"):
                if col not in data.columns:
                    return []
            if len(data) < 20:
                return []

            vwap_series = context.get("vwap_series")
            if vwap_series is None:
                vwap_value = context.get("vwap_value")
                if vwap_value is None:
                    return []
                vwap_series = pd.Series(float(vwap_value), index=data.index)
            else:
                vwap_series = pd.Series(vwap_series).reindex(data.index).ffill()

            atr = context.get("atr_15m_14")
            if atr is None:
                tr = (data["high"] - data["low"]).abs()
                atr = float(tr.rolling(14).mean().iloc[-1]) if not tr.empty else 0.0
            atr = float(atr)
            if atr <= 0:
                return []

            signals: List[Dict[str, Any]] = []
            for i in range(1, len(data)):
                row = data.iloc[i]
                prev = data.iloc[i - 1]
                vwap = float(vwap_series.iloc[i])
                close = float(row["close"])
                open_ = float(row["open"])
                ext_mult = abs(close - vwap) / atr
                if ext_mult < 1.5:
                    continue

                if close < vwap:
                    reversal = close > open_ and float(prev["close"]) <= float(prev["open"])
                    if not reversal:
                        continue
                    entry = close
                    stop = float(row["low"]) - (2 * self.tick_size)
                    target_1 = vwap
                    target_2 = vwap + 0.5 * atr
                    strategy = "MEAN_REVERSION_LONG"
                    full_name = "Mean Reversion to VWAP — Long"
                    desc_side = "below"
                else:
                    reversal = close < open_ and float(prev["close"]) >= float(prev["open"])
                    if not reversal:
                        continue
                    entry = close
                    stop = float(row["high"]) + (2 * self.tick_size)
                    target_1 = vwap
                    target_2 = vwap - 0.5 * atr
                    strategy = "MEAN_REVERSION_SHORT"
                    full_name = "Mean Reversion to VWAP — Short"
                    desc_side = "above"

                confidence = 0.55
                if ext_mult >= 2.5:
                    confidence += 0.15
                elif ext_mult >= 1.8:
                    confidence += 0.07

                signals.append(
                    {
                        "strategy": strategy,
                        "strategy_full_name": full_name,
                        "entry": float(entry),
                        "stop_loss": float(stop),
                        "target_1": float(target_1),
                        "target_2": float(target_2),
                        "confidence": float(round(min(1.0, confidence), 2)),
                        "extension_atr_multiple": float(round(ext_mult, 2)),
                        "requires_ranging_market": True,
                        "description": f"{full_name}: price extended {ext_mult:.2f} ATR {desc_side} VWAP and reversed.",
                    }
                )

            signals.sort(key=lambda x: x["confidence"], reverse=True)
            return signals
        except Exception as exc:
            logger.exception("detect_mean_reversion failed: {}", exc)
            return []
