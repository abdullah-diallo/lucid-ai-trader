"""
P03 Strategy B: Fibonacci retracement strategy.
"""

from __future__ import annotations

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


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize index to timezone-aware US/Eastern index."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class FibonacciStrategy:
    """Finds impulse moves and golden-pocket retracement entries."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size

    def detect_impulse_move(self, df: pd.DataFrame, min_size_atr_multiple: float = 2.0) -> list:
        """Detect strong impulse moves suitable for Fibonacci retracement work."""
        try:
            data = _normalize_df(df)
            for col in ("open", "high", "low", "close"):
                if col not in data.columns:
                    return []
            if len(data) < 20:
                return []

            tr = (data["high"] - data["low"]).abs()
            atr = tr.rolling(14).mean()
            impulses: List[Dict[str, Any]] = []

            i = 14
            while i < len(data):
                direction = None
                seq_start = i
                seq_end = i

                for j in range(i, len(data)):
                    o = float(data["open"].iloc[j])
                    c = float(data["close"].iloc[j])
                    d = "BULL" if c > o else ("BEAR" if c < o else "FLAT")
                    if direction is None and d in {"BULL", "BEAR"}:
                        direction = d
                        seq_start = j
                        seq_end = j
                    elif direction is not None and d == direction:
                        seq_end = j
                    elif direction is not None:
                        break

                if direction is None:
                    i += 1
                    continue

                consec = seq_end - seq_start + 1
                move_start = float(data["open"].iloc[seq_start])
                move_end = float(data["close"].iloc[seq_end])
                move_size = abs(move_end - move_start)
                atr_ref = float(atr.iloc[seq_end]) if not pd.isna(atr.iloc[seq_end]) else 0.0
                size_atr = (move_size / atr_ref) if atr_ref > 0 else 0.0

                displacement_ok = False
                if seq_start == seq_end:
                    rng = float(data["high"].iloc[seq_end] - data["low"].iloc[seq_end])
                    body = abs(float(data["close"].iloc[seq_end] - data["open"].iloc[seq_end]))
                    displacement_ok = rng > 0 and (body / rng) >= 0.7 and size_atr >= min_size_atr_multiple

                if (consec >= 3 or displacement_ok) and size_atr >= min_size_atr_multiple:
                    impulses.append(
                        {
                            "direction": direction,
                            "start_price": move_start,
                            "end_price": move_end,
                            "size_atr": float(round(size_atr, 2)),
                            "timestamp_start": data.index[seq_start].to_pydatetime(),
                            "timestamp_end": data.index[seq_end].to_pydatetime(),
                        }
                    )
                    i = seq_end + 1
                else:
                    i += 1
            return impulses
        except Exception as exc:
            logger.exception("detect_impulse_move failed: {}", exc)
            return []

    def calculate_fib_levels(self, impulse: dict) -> dict:
        """Calculate key Fibonacci levels and golden pocket from one impulse."""
        try:
            start = float(impulse["start_price"])
            end = float(impulse["end_price"])
            direction = impulse["direction"]
            swing = abs(end - start)
            if swing <= 0:
                raise ValueError("Impulse swing size is zero")

            if direction == "BULL":
                lv = {
                    "fib_0": end,
                    "fib_236": end - (swing * 0.236),
                    "fib_382": end - (swing * 0.382),
                    "fib_500": end - (swing * 0.500),
                    "fib_618": end - (swing * 0.618),
                    "fib_650": end - (swing * 0.650),
                    "fib_705": end - (swing * 0.705),
                    "fib_786": end - (swing * 0.786),
                    "fib_100": start,
                }
            else:
                lv = {
                    "fib_0": end,
                    "fib_236": end + (swing * 0.236),
                    "fib_382": end + (swing * 0.382),
                    "fib_500": end + (swing * 0.500),
                    "fib_618": end + (swing * 0.618),
                    "fib_650": end + (swing * 0.650),
                    "fib_705": end + (swing * 0.705),
                    "fib_786": end + (swing * 0.786),
                    "fib_100": start,
                }

            lv["golden_pocket_top"] = lv["fib_618"]
            lv["golden_pocket_bottom"] = lv["fib_705"]
            lv["ote_level"] = lv["fib_618"]
            return lv
        except Exception as exc:
            logger.exception("calculate_fib_levels failed: {}", exc)
            return {}

    def detect_fib_entry(self, df: pd.DataFrame, impulse: dict, fib_levels: dict, context: dict) -> dict | None:
        """Detect a valid golden-pocket retracement entry with confluence."""
        try:
            if not fib_levels:
                return None
            data = _normalize_df(df)
            if data.empty:
                return None

            direction = impulse["direction"]
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
            if direction == "BULL" and not (h4 in {"BULLISH", "NEUTRAL"} and h1 in {"BULLISH", "NEUTRAL"}):
                return None
            if direction == "BEAR" and not (h4 in {"BEARISH", "NEUTRAL"} and h1 in {"BEARISH", "NEUTRAL"}):
                return None

            gp_top = max(float(fib_levels["golden_pocket_top"]), float(fib_levels["golden_pocket_bottom"]))
            gp_bottom = min(float(fib_levels["golden_pocket_top"]), float(fib_levels["golden_pocket_bottom"]))
            fib_786 = float(fib_levels["fib_786"])

            for i in range(1, len(data)):
                row = data.iloc[i]
                prev = data.iloc[i - 1]
                o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
                in_zone = h >= gp_bottom and l <= gp_top
                if not in_zone:
                    continue

                if direction == "BULL":
                    invalid = c < fib_786
                    reject = c > o and float(prev["close"]) <= float(prev["open"])
                    if invalid or not reject:
                        continue
                    entry = max(float(fib_levels["fib_618"]), c)
                    stop = fib_786 - (2 * self.tick_size)
                    target_1 = float(fib_levels["fib_0"])
                    swing = abs(float(impulse["end_price"]) - float(impulse["start_price"]))
                    target_2 = target_1 + (swing * 0.272)
                    target_3 = target_1 + (swing * 0.618)
                    strategy = "FIB_RETRACEMENT_LONG"
                    full_name = "Fibonacci Golden Pocket Retracement — Long"
                else:
                    invalid = c > fib_786
                    reject = c < o and float(prev["close"]) >= float(prev["open"])
                    if invalid or not reject:
                        continue
                    entry = min(float(fib_levels["fib_618"]), c)
                    stop = fib_786 + (2 * self.tick_size)
                    target_1 = float(fib_levels["fib_0"])
                    swing = abs(float(impulse["end_price"]) - float(impulse["start_price"]))
                    target_2 = target_1 - (swing * 0.272)
                    target_3 = target_1 - (swing * 0.618)
                    strategy = "FIB_RETRACEMENT_SHORT"
                    full_name = "Fibonacci Golden Pocket Retracement — Short"

                confluence: List[str] = []
                score = 0.58

                fvg_hit = False
                ob_hit = False
                for f in context.get("fvgs", {}).get("5m", {}).get("standard", []):
                    if float(f.get("bottom", gp_bottom - 1)) <= gp_top and float(f.get("top", gp_top + 1)) >= gp_bottom:
                        fvg_hit = True
                        break
                for ob in context.get("order_blocks", {}).get("5m", {}).get("standard", []):
                    if float(ob.get("low", gp_bottom - 1)) <= gp_top and float(ob.get("high", gp_top + 1)) >= gp_bottom:
                        ob_hit = True
                        break
                if fvg_hit:
                    score += 0.15
                    confluence.append("FVG in golden pocket")
                if ob_hit:
                    score += 0.12
                    confluence.append("Order Block in golden pocket")

                vwap = context.get("vwap_value")
                if vwap is not None and gp_bottom <= float(vwap) <= gp_top:
                    score += 0.10
                    confluence.append("VWAP at golden pocket")

                return {
                    "strategy": strategy,
                    "strategy_full_name": full_name,
                    "entry": float(entry),
                    "stop_loss": float(stop),
                    "target_1": float(target_1),
                    "target_2": float(target_2),
                    "target_3": float(target_3),
                    "golden_pocket_zone": {"top": float(gp_top), "bottom": float(gp_bottom)},
                    "impulse_size_points": float(round(abs(float(impulse["end_price"]) - float(impulse["start_price"])), 4)),
                    "fib_confluence": confluence,
                    "confidence": float(round(min(1.0, score), 2)),
                    "description": f"{full_name}: retracement into golden pocket with rejection confirmation.",
                }
            return None
        except Exception as exc:
            logger.exception("detect_fib_entry failed: {}", exc)
            return None
