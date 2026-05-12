"""
ICT/SMC orchestration engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from analysis.strategy_bos import BOSEntryStrategy
from analysis.strategy_smc import SMCFrameworkStrategy


class ICTSMCEngine:
    """Runs BOS and strict SMC strategies and merges confluence output."""

    def __init__(self) -> None:
        self.bos_strategy = BOSEntryStrategy()
        self.smc_strategy = SMCFrameworkStrategy()

    def detect_fvg_trade(self, context: dict, current_price: float) -> list:
        """Detect fresh FVG/IFVG entries aligned with HTF bias."""
        try:
            signals: List[Dict[str, Any]] = []
            h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
            h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
            if h4 not in {"BULLISH", "BEARISH"} or h1 not in {"BULLISH", "BEARISH", "RANGING"}:
                return signals

            now_dt = context.get("generated_at", datetime.now(tz=pytz.utc))
            if now_dt.tzinfo is None:
                now_dt = pytz.utc.localize(now_dt)

            for tf in ("15m", "5m"):
                fvg_data = context.get("fvgs", {}).get(tf, {})
                candidates = []
                for f in fvg_data.get("standard", []):
                    f_local = dict(f)
                    f_local["is_inverse"] = False
                    candidates.append(f_local)
                for f in fvg_data.get("inverse", []):
                    f_local = dict(f)
                    f_local["is_inverse"] = True
                    candidates.append(f_local)

                for fvg in candidates:
                    age = int(fvg.get("age_bars", 999))
                    filled = bool(fvg.get("filled", False))
                    if age > 20:
                        continue
                    if not fvg.get("is_inverse") and filled:
                        continue

                    ftype = str(fvg.get("type", ""))
                    top = float(fvg.get("top"))
                    bottom = float(fvg.get("bottom"))
                    midpoint = float(fvg.get("midpoint", (top + bottom) / 2.0))
                    direction = None
                    if ftype == "BULL_FVG" and h4 == "BULLISH" and h1 in {"BULLISH", "RANGING"}:
                        direction = "LONG"
                    if ftype == "BEAR_FVG" and h4 == "BEARISH" and h1 in {"BEARISH", "RANGING"}:
                        direction = "SHORT"
                    if direction is None:
                        continue

                    entered_zone = bottom <= float(current_price) <= top
                    edge_touch = (direction == "LONG" and current_price <= top) or (direction == "SHORT" and current_price >= bottom)
                    if not (entered_zone or edge_touch):
                        continue

                    if direction == "LONG":
                        entry = midpoint
                        stop = bottom - 0.5
                        swings = context.get("market_structure", {}).get(tf, {}).get("swings", {}).get("swing_highs", [])
                        t1 = min([float(x["price"]) for x in swings if float(x["price"]) > entry], default=top + (top - stop))
                        t2 = float(fvg.get("price_origin", top))
                        bsl = context.get("liquidity_pools", {}).get(tf, {}).get("bsl_levels", [])
                        t3 = min([float(x["price"]) for x in bsl if float(x["price"]) > entry], default=t1)
                    else:
                        entry = midpoint
                        stop = top + 0.5
                        swings = context.get("market_structure", {}).get(tf, {}).get("swings", {}).get("swing_lows", [])
                        t1 = max([float(x["price"]) for x in swings if float(x["price"]) < entry], default=bottom - (stop - bottom))
                        t2 = float(fvg.get("price_origin", bottom))
                        ssl = context.get("liquidity_pools", {}).get(tf, {}).get("ssl_levels", [])
                        t3 = max([float(x["price"]) for x in ssl if float(x["price"]) < entry], default=t1)

                    score = 0.58 - (0.05 if fvg.get("is_inverse") else 0.0)
                    confluences: List[str] = []

                    has_ob_overlap = any(
                        float(ob.get("low", bottom - 1)) <= top and float(ob.get("high", top + 1)) >= bottom
                        for ob in context.get("order_blocks", {}).get(tf, {}).get("standard", [])
                    )
                    if has_ob_overlap:
                        score += 0.12
                        confluences.append("OB + FVG overlap")

                    if (direction == "LONG" and h4 == "BULLISH") or (direction == "SHORT" and h4 == "BEARISH"):
                        score += 0.10
                        confluences.append("4H trend agreement")

                    fib = context.get("fibonacci_levels", {})
                    fib_levels = [fib.get("fib_618"), fib.get("fib_786")]
                    if any(l is not None and abs(midpoint - float(l)) / max(abs(midpoint), 1e-9) <= 0.002 for l in fib_levels):
                        score += 0.08
                        confluences.append("Fib 0.618/0.786 confluence")

                    et = now_dt.astimezone(pytz.timezone("US/Eastern")).time()
                    is_kz = (et >= datetime.strptime("02:00", "%H:%M").time() and et < datetime.strptime("05:00", "%H:%M").time()) or (
                        et >= datetime.strptime("07:00", "%H:%M").time() and et < datetime.strptime("10:00", "%H:%M").time()
                    ) or (et >= datetime.strptime("08:00", "%H:%M").time() and et < datetime.strptime("12:00", "%H:%M").time())
                    if is_kz:
                        score += 0.07
                        confluences.append("Kill zone timing")

                    vwap_bias = str(context.get("vwap_position", {}).get("bias", "NEUTRAL")).upper()
                    if (direction == "LONG" and vwap_bias == "BULLISH") or (direction == "SHORT" and vwap_bias == "BEARISH"):
                        score += 0.05
                        confluences.append("VWAP confirms direction")

                    if age < 10:
                        score += 0.05
                        confluences.append("Fresh FVG")
                    if age > 20:
                        score -= 0.08
                    if abs(top - bottom) < 1.0:
                        score -= 0.10
                        confluences.append("Small FVG size")

                    score = max(0.0, min(1.0, score))
                    strategy = (
                        "IFVG_LONG"
                        if fvg.get("is_inverse") and direction == "LONG"
                        else "IFVG_SHORT"
                        if fvg.get("is_inverse")
                        else "FVG_LONG"
                        if direction == "LONG"
                        else "FVG_SHORT"
                    )
                    full_name = (
                        "Inverse FVG — Long"
                        if strategy == "IFVG_LONG"
                        else "Inverse FVG — Short"
                        if strategy == "IFVG_SHORT"
                        else "Fair Value Gap Entry — Long"
                        if strategy == "FVG_LONG"
                        else "Fair Value Gap Entry — Short"
                    )
                    signals.append(
                        {
                            "strategy": strategy,
                            "strategy_full_name": full_name,
                            "entry": float(entry),
                            "stop_loss": float(stop),
                            "target_1": float(t1),
                            "target_2": float(t2),
                            "target_3": float(t3),
                            "confidence": float(round(score, 2)),
                            "is_inverse": bool(fvg.get("is_inverse", False)),
                            "timeframe": tf,
                            "fvg_zone": {"top": top, "bottom": bottom, "midpoint": midpoint},
                            "confluence_factors": confluences,
                            "description": f"{full_name}: price tapped {tf} FVG and offers midpoint entry in HTF direction.",
                        }
                    )

            signals.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            return signals
        except Exception as exc:
            logger.exception("detect_fvg_trade failed: {}", exc)
            return []

    def run_all_smc_strategies(self, context: dict, df_dict: dict | None = None) -> list:
        """Run BOS + SMC strategies and return highest-confidence signals first."""
        try:
            logger.info("Running all SMC strategies")
            df_dict = df_dict or {}
            signals: List[Dict[str, Any]] = []

            bos_signals = self.bos_strategy.detect_bos_entry_setup(df_dict=df_dict, context=context)
            current_price = float(context.get("current_price", 0.0))
            current_dt = context.get("generated_at", datetime.now(tz=pytz.utc))
            smc_score = self.smc_strategy.score_smc_setup(context=context, current_price=current_price, current_dt=current_dt)
            smc_signal = self.smc_strategy.generate_smc_signal(context=context, smc_score=smc_score)
            fvg_signals = self.detect_fvg_trade(context=context, current_price=current_price)

            if bos_signals:
                signals.extend(bos_signals)
            if smc_signal:
                signals.append(smc_signal)
            if fvg_signals:
                signals.extend(fvg_signals)

            if bos_signals and smc_signal:
                best_bos = max(bos_signals, key=lambda x: float(x.get("confidence", 0.0)))
                merged = dict(best_bos)
                merged["strategy"] = "BOS + SMC CONFLUENCE"
                merged["strategy_full_name"] = "BOS + SMC CONFLUENCE"
                merged["confidence"] = round(max(float(best_bos.get("confidence", 0.0)), float(smc_signal.get("confidence", 0.0))), 2)
                merged["smc_score"] = smc_signal.get("smc_score")
                merged["pillar_scores"] = smc_signal.get("pillar_scores", {})
                merged["poi_used"] = smc_signal.get("poi_used")
                merged["confluence_factors"] = list(dict.fromkeys((best_bos.get("confluence_factors", []) + smc_signal.get("confluence_factors", []))))
                merged["description"] = f"{best_bos.get('description')} | SMC confirmed with score {smc_signal.get('smc_score')}."
                signals = [merged] + [s for s in signals if s is not best_bos and s is not smc_signal]

            signals.sort(key=lambda x: float(x.get("confidence", x.get("smc_score", 0.0))), reverse=True)
            return signals
        except Exception as exc:
            logger.exception("run_all_smc_strategies failed: {}", exc)
            return []
