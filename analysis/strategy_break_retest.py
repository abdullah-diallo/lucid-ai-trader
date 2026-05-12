"""
Strategy B: Break and Retest of key levels.
"""

from __future__ import annotations

from datetime import datetime, time
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


def _to_eastern_idx(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame index to US/Eastern timezone."""
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC").tz_convert(EASTERN)
    else:
        out.index = out.index.tz_convert(EASTERN)
    return out


class BreakRetestStrategy:
    """Detects clean break-and-retest setups across key levels."""

    def __init__(self, tick_size: float = 0.25, instrument: str = "MES") -> None:
        self.tick_size = tick_size
        self.instrument = instrument.upper()

    def get_key_levels(self, df_dict: dict, context: dict) -> list:
        """Compile major/minor key levels from sessions, structure, VWAP, ORB and round numbers."""
        try:
            levels: List[Dict[str, Any]] = []
            d1 = _to_eastern_idx(df_dict["1D"]) if "1D" in df_dict else None
            m5 = _to_eastern_idx(df_dict["5m"]) if "5m" in df_dict else None
            if d1 is not None and len(d1) >= 2:
                prev = d1.iloc[-2]
                levels.extend(
                    [
                        {"price": float(prev["high"]), "type": "Prior Day High", "strength": "MAJOR"},
                        {"price": float(prev["low"]), "type": "Prior Day Low", "strength": "MAJOR"},
                    ]
                )

            if m5 is not None and not m5.empty:
                first_bar = m5.iloc[0]
                levels.append({"price": float(first_bar["open"]), "type": "Weekly Open Proxy", "strength": "MAJOR"})

                asia = m5.between_time("20:00", "00:00", inclusive="both")
                london = m5.between_time("02:00", "05:00", inclusive="both")
                if not asia.empty:
                    levels.extend(
                        [
                            {"price": float(asia["high"].max()), "type": "Asia High", "strength": "MAJOR"},
                            {"price": float(asia["low"].min()), "type": "Asia Low", "strength": "MAJOR"},
                        ]
                    )
                if not london.empty:
                    levels.extend(
                        [
                            {"price": float(london["high"].max()), "type": "London High", "strength": "MAJOR"},
                            {"price": float(london["low"].min()), "type": "London Low", "strength": "MAJOR"},
                        ]
                    )

                last_px = float(m5["close"].iloc[-1])
                step = 25.0 if self.instrument == "MES" else 100.0
                anchor = round(last_px / step) * step
                for k in range(-3, 4):
                    levels.append(
                        {"price": float(anchor + k * step), "type": "Round Number", "strength": "MINOR"}
                    )

            for tf in ("15m", "5m", "1H"):
                for ev in context.get("market_structure", {}).get(tf, {}).get("bos_choch", []):
                    if "BOS" in str(ev.get("type", "")):
                        levels.append(
                            {
                                "price": float(ev.get("price_level")),
                                "type": f"{tf} BOS Level",
                                "strength": "MAJOR",
                            }
                        )

            vwap_value = context.get("vwap_value")
            if vwap_value is not None:
                levels.append({"price": float(vwap_value), "type": "VWAP", "strength": "MAJOR"})

            orb = context.get("orb_data", {})
            if orb and orb.get("established"):
                levels.append({"price": float(orb["orb_high"]), "type": "ORB High", "strength": "MAJOR"})
                levels.append({"price": float(orb["orb_low"]), "type": "ORB Low", "strength": "MAJOR"})

            unique = {}
            for lvl in levels:
                key = (round(float(lvl["price"]), 3), lvl["type"])
                unique[key] = lvl
            return list(unique.values())
        except Exception as exc:
            logger.exception("get_key_levels failed: {}", exc)
            return []

    def _kill_zone(self, dt: datetime) -> bool:
        """Return True for London and NY open kill zones."""
        et = dt.astimezone(EASTERN) if dt.tzinfo else pytz.utc.localize(dt).astimezone(EASTERN)
        t = et.time()
        london = time(2, 0) <= t < time(5, 0)
        ny_open = time(7, 0) <= t < time(10, 0)
        overlap = time(8, 0) <= t < time(12, 0)
        return london or ny_open or overlap

    def detect_break_retest(self, df: pd.DataFrame, key_levels: list, context: dict) -> list:
        """Find clean break, timely retest, and rejection entries against key levels."""
        try:
            data = _to_eastern_idx(df)
            if data.empty:
                return []
            for c in ("open", "high", "low", "close"):
                if c not in data.columns:
                    return []

            volume_avg = data["volume"].rolling(20).mean() if "volume" in data.columns else None
            signals: List[Dict[str, Any]] = []
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            vwap_bias = str(context.get("vwap_position", {}).get("bias", "NEUTRAL")).upper()
            news_soon = bool(context.get("news_within_30m", False))

            for lvl in key_levels:
                level = float(lvl["price"])
                level_type = str(lvl["type"])
                strength = str(lvl["strength"])

                for i in range(20, len(data) - 12):
                    row = data.iloc[i]
                    close = float(row["close"])
                    open_ = float(row["open"])
                    high = float(row["high"])
                    low = float(row["low"])

                    long_break = close > (level + 0.5)
                    short_break = close < (level - 0.5)
                    if not long_break and not short_break:
                        continue

                    if volume_avg is not None and not pd.isna(volume_avg.iloc[i]):
                        if float(data["volume"].iloc[i]) <= float(volume_avg.iloc[i]):
                            continue

                    direction = "LONG" if long_break else "SHORT"
                    window = data.iloc[i + 1 : i + 13]
                    if window.empty:
                        continue

                    retest_row = None
                    tol = 0.2
                    for j in range(len(window)):
                        r = window.iloc[j]
                        touch = float(r["low"]) <= level + tol and float(r["high"]) >= level - tol
                        if not touch:
                            continue
                        if direction == "LONG":
                            valid = float(r["close"]) >= level
                            wick_ratio = (min(float(r["open"]), float(r["close"])) - float(r["low"])) / max(
                                float(r["high"]) - float(r["low"]), 1e-9
                            )
                        else:
                            valid = float(r["close"]) <= level
                            wick_ratio = (float(r["high"]) - max(float(r["open"]), float(r["close"]))) / max(
                                float(r["high"]) - float(r["low"]), 1e-9
                            )
                        if valid:
                            retest_row = (window.index[j], r, wick_ratio)
                            break
                    if retest_row is None:
                        continue

                    ts, r, wick_ratio = retest_row
                    entry = float(r["close"])
                    stop = level - (2 * self.tick_size) if direction == "LONG" else level + (2 * self.tick_size)

                    next_levels = sorted([float(x["price"]) for x in key_levels if float(x["price"]) > entry])
                    prev_levels = sorted([float(x["price"]) for x in key_levels if float(x["price"]) < entry])
                    if direction == "LONG":
                        t1 = next_levels[0] if next_levels else entry + 1.5 * (entry - stop)
                        t2 = next_levels[1] if len(next_levels) > 1 else entry + 2.2 * (entry - stop)
                        liq = context.get("liquidity_pools", {}).get("5m", {}).get("bsl_levels", [])
                        t3 = min([float(x["price"]) for x in liq if float(x["price"]) > entry], default=t2)
                        strategy = "BREAK_RETEST_LONG"
                        full_name = "Break & Retest of Key Level — Long"
                    else:
                        t1 = prev_levels[-1] if prev_levels else entry - 1.5 * (stop - entry)
                        t2 = prev_levels[-2] if len(prev_levels) > 1 else entry - 2.2 * (stop - entry)
                        liq = context.get("liquidity_pools", {}).get("5m", {}).get("ssl_levels", [])
                        t3 = max([float(x["price"]) for x in liq if float(x["price"]) < entry], default=t2)
                        strategy = "BREAK_RETEST_SHORT"
                        full_name = "Break & Retest of Key Level — Short"

                    rr1 = abs((t1 - entry) / (entry - stop)) if entry != stop else 0.0
                    if rr1 < 1.5:
                        continue

                    score = 0.50
                    confluences: List[str] = []
                    if strength == "MAJOR":
                        score += 0.12
                        confluences.append("Major level")
                    else:
                        score -= 0.10
                        confluences.append("Minor level")

                    if (direction == "LONG" and h4 == "BULLISH") or (direction == "SHORT" and h4 == "BEARISH"):
                        score += 0.10
                        confluences.append("4H trend agreement")
                    elif h4 in {"BULLISH", "BEARISH"}:
                        score -= 0.10
                        confluences.append("Against 4H trend")

                    fvg_near = False
                    for f in context.get("fvgs", {}).get("5m", {}).get("standard", []):
                        mid = float(f.get("midpoint", 0.0))
                        if abs(mid - level) <= 0.2:
                            fvg_near = True
                            break
                    if fvg_near:
                        score += 0.08
                        confluences.append("FVG at retest")

                    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else datetime.now(tz=EASTERN)
                    if self._kill_zone(dt):
                        score += 0.08
                        confluences.append("Kill zone timing")

                    if (direction == "LONG" and vwap_bias == "BULLISH") or (direction == "SHORT" and vwap_bias == "BEARISH"):
                        score += 0.05
                        confluences.append("VWAP confirms")

                    if wick_ratio > 0.60:
                        score += 0.05
                        confluences.append("Strong rejection wick")

                    if news_soon:
                        score -= 0.15
                        confluences.append("News risk within 30m")

                    score = max(0.0, min(1.0, score))
                    signals.append(
                        {
                            "strategy": strategy,
                            "strategy_full_name": full_name,
                            "level_type": level_type,
                            "entry": float(entry),
                            "stop_loss": float(stop),
                            "target_1": float(t1),
                            "target_2": float(t2),
                            "target_3": float(t3),
                            "confidence": float(round(score, 2)),
                            "confluence_factors": confluences,
                            "description": f"{full_name}: clean break/retest of {level_type} at {level:.2f}.",
                        }
                    )

            signals.sort(key=lambda x: x["confidence"], reverse=True)
            return signals
        except Exception as exc:
            logger.exception("detect_break_retest failed: {}", exc)
            return []
