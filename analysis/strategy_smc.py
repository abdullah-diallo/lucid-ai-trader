"""
Smart Money Concepts full-framework strategy (P07).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz

try:
    from loguru import logger
except Exception:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from analysis.trading_concepts import EASTERN


class SMCFrameworkStrategy:
    """Strict 5-pillar SMC scoring and signal generation."""

    def __init__(self, tick_size: float = 0.25) -> None:
        self.tick_size = tick_size
        self.weights = {
            "Higher Timeframe Bias": 0.25,
            "Liquidity Swept": 0.20,
            "Point of Interest Quality": 0.25,
            "Premium/Discount Position": 0.15,
            "Session Timing": 0.15,
        }
        self.minimums = {
            "Higher Timeframe Bias": 0.70,
            "Liquidity Swept": 0.50,
            "Point of Interest Quality": 0.60,
            "Premium/Discount Position": 0.50,
            "Session Timing": 0.50,
        }

    def _infer_direction(self, context: dict) -> str:
        """Infer trade direction from HTF bias."""
        d = str(context.get("market_structure", {}).get("1D", {}).get("trend", "RANGING")).upper()
        h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
        if d == h4 and d in {"BULLISH", "BEARISH"}:
            return d
        return "RANGING"

    def _score_htf_bias(self, context: dict) -> float:
        """Score daily/4H/1H directional agreement."""
        d = str(context.get("market_structure", {}).get("1D", {}).get("trend", "RANGING")).upper()
        h4 = str(context.get("market_structure", {}).get("4H", {}).get("trend", "RANGING")).upper()
        h1 = str(context.get("market_structure", {}).get("1H", {}).get("trend", "RANGING")).upper()
        if d != h4 or d == "RANGING":
            return 0.0
        if h1 == d:
            return 1.0
        if h1 == "RANGING":
            return 0.7
        return 0.4

    def _score_liquidity(self, context: dict) -> float:
        """Score recent sweep quality."""
        sweeps = context.get("liquidity_sweeps", {}).get("5m", [])
        if sweeps:
            recent = sweeps[-5:]
            if any(bool(s.get("reversal_signal")) for s in recent):
                return 1.0
            return 0.6

        near = context.get("nearest_poi")
        price = context.get("current_price")
        if near is not None and price is not None and abs(float(near) - float(price)) / max(abs(float(price)), 1e-9) <= 0.003:
            return 0.6
        return 0.0

    def _score_poi(self, context: dict, current_price: float) -> Dict[str, Any]:
        """Score POI quality from OB/FVG/Breaker proximity."""
        tf = "5m"
        obs = context.get("order_blocks", {}).get(tf, {}).get("standard", [])
        breakers = context.get("order_blocks", {}).get(tf, {}).get("breakers", [])
        fvgs = context.get("fvgs", {}).get(tf, {}).get("standard", [])
        ifvgs = context.get("fvgs", {}).get(tf, {}).get("inverse", [])

        in_ob = next((ob for ob in obs if float(ob["low"]) <= current_price <= float(ob["high"]) and not ob.get("mitigated", False)), None)
        in_fvg = next((f for f in fvgs if float(f["bottom"]) <= current_price <= float(f["top"])), None)
        in_ifvg = next((f for f in ifvgs if float(f["bottom"]) <= current_price <= float(f["top"])), None)
        in_breaker = next((b for b in breakers if float(b["low"]) <= current_price <= float(b["high"])), None)

        if in_ob and in_fvg:
            poi = "FVG + OB Overlap"
            score = 1.0
            poi_obj = in_ob
        elif in_ob or in_fvg:
            poi = "Order Block" if in_ob else "FVG"
            score = 0.8
            poi_obj = in_ob if in_ob else in_fvg
        elif in_ifvg or in_breaker:
            poi = "IFVG / Breaker"
            score = 0.6
            poi_obj = in_breaker if in_breaker else in_ifvg
        else:
            nearest = context.get("nearest_poi")
            if nearest is not None and abs(float(nearest) - current_price) / max(abs(current_price), 1e-9) <= 0.002:
                poi = "Near POI"
                score = 0.3
                poi_obj = {"midpoint": float(nearest), "low": float(nearest), "high": float(nearest)}
            else:
                poi = "None"
                score = 0.0
                poi_obj = None
        return {"score": score, "poi": poi, "poi_obj": poi_obj}

    def _score_pd(self, context: dict, direction: str, current_price: float) -> float:
        """Score premium/discount alignment."""
        zone = str(context.get("premium_discount", {}).get("zone", "EQUILIBRIUM")).upper()
        ote = context.get("premium_discount", {}).get("ote_level")
        if direction == "BULLISH":
            if zone == "DISCOUNT":
                if ote and abs(current_price - float(ote)) / max(abs(float(ote)), 1e-9) <= 0.0015:
                    return 1.0
                return 0.7
            if zone == "EQUILIBRIUM":
                return 0.2
            return 0.0
        if direction == "BEARISH":
            if zone == "PREMIUM":
                if ote and abs(current_price - float(ote)) / max(abs(float(ote)), 1e-9) <= 0.0015:
                    return 1.0
                return 0.7
            if zone == "EQUILIBRIUM":
                return 0.2
            return 0.0
        return 0.0

    def _score_session(self, current_dt: datetime) -> float:
        """Score session timing quality."""
        et = current_dt.astimezone(EASTERN) if current_dt.tzinfo else pytz.utc.localize(current_dt).astimezone(EASTERN)
        t = et.time()
        if t >= datetime.strptime("08:00", "%H:%M").time() and t < datetime.strptime("12:00", "%H:%M").time():
            return 1.0
        if t >= datetime.strptime("07:00", "%H:%M").time() and t < datetime.strptime("10:00", "%H:%M").time():
            return 0.9
        if t >= datetime.strptime("02:00", "%H:%M").time() and t < datetime.strptime("05:00", "%H:%M").time():
            return 0.8
        if t >= datetime.strptime("14:00", "%H:%M").time() and t < datetime.strptime("16:00", "%H:%M").time():
            return 0.3
        return 0.0

    def score_smc_setup(self, context: dict, current_price: float, current_dt: datetime) -> dict:
        """Compute strict 5-pillar SMC score with per-pillar minimum checks."""
        try:
            logger.info("Scoring SMC setup")
            direction = self._infer_direction(context)
            p1 = self._score_htf_bias(context)
            p2 = self._score_liquidity(context)
            poi_meta = self._score_poi(context, current_price)
            p3 = poi_meta["score"]
            p4 = self._score_pd(context, direction, current_price)
            p5 = self._score_session(current_dt)

            pillar_scores = {
                "Higher Timeframe Bias": p1,
                "Liquidity Swept": p2,
                "Point of Interest Quality": p3,
                "Premium/Discount Position": p4,
                "Session Timing": p5,
            }
            weighted = sum(pillar_scores[k] * self.weights[k] for k in pillar_scores)
            passed = all(pillar_scores[k] >= self.minimums[k] for k in pillar_scores) and weighted >= 0.72
            failed_pillars = [k for k in pillar_scores if pillar_scores[k] < self.minimums[k]]

            return {
                "passes": passed,
                "smc_score": round(weighted, 4),
                "pillar_scores": pillar_scores,
                "failed_pillars": failed_pillars,
                "direction": direction,
                "poi_used": poi_meta["poi"],
                "poi_obj": poi_meta["poi_obj"],
            }
        except Exception as exc:
            logger.exception("score_smc_setup failed: {}", exc)
            return {
                "passes": False,
                "smc_score": 0.0,
                "pillar_scores": {},
                "failed_pillars": ["ERROR"],
                "direction": "RANGING",
                "poi_used": "None",
                "poi_obj": None,
            }

    def generate_smc_signal(self, context: dict, smc_score: dict) -> dict | None:
        """Generate final SMC signal if all strict conditions are met."""
        try:
            if not smc_score.get("passes"):
                return None

            direction = smc_score["direction"]
            poi_obj = smc_score.get("poi_obj") or {}
            current_price = float(context.get("current_price"))
            midpoint = float(poi_obj.get("midpoint", current_price))
            low = float(poi_obj.get("low", midpoint))
            high = float(poi_obj.get("high", midpoint))

            if direction == "BULLISH":
                strategy = "SMC_LONG"
                full_name = "Smart Money Concepts — Full Confluence Long"
                entry = midpoint
                stop = low - (2 * self.tick_size)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_highs", [])
                target_1 = min([float(x["price"]) for x in swings if float(x["price"]) > entry], default=entry + (entry - stop))
                bsl = context.get("liquidity_pools", {}).get("5m", {}).get("bsl_levels", [])
                target_2 = min([float(x["price"]) for x in bsl if float(x["price"]) > entry], default=target_1)
                htf_bsl = context.get("liquidity_pools", {}).get("4H", {}).get("bsl_levels", [])
                target_3 = min([float(x["price"]) for x in htf_bsl if float(x["price"]) > entry], default=target_2)
                liq_target = target_2
            else:
                strategy = "SMC_SHORT"
                full_name = "Smart Money Concepts — Full Confluence Short"
                entry = midpoint
                stop = high + (2 * self.tick_size)
                swings = context.get("market_structure", {}).get("5m", {}).get("swings", {}).get("swing_lows", [])
                target_1 = max([float(x["price"]) for x in swings if float(x["price"]) < entry], default=entry - (stop - entry))
                ssl = context.get("liquidity_pools", {}).get("5m", {}).get("ssl_levels", [])
                target_2 = max([float(x["price"]) for x in ssl if float(x["price"]) < entry], default=target_1)
                htf_ssl = context.get("liquidity_pools", {}).get("4H", {}).get("ssl_levels", [])
                target_3 = max([float(x["price"]) for x in htf_ssl if float(x["price"]) < entry], default=target_2)
                liq_target = target_2

            confluences = [
                f"HTF Bias {smc_score['pillar_scores'].get('Higher Timeframe Bias', 0):.2f}",
                f"Liquidity {smc_score['pillar_scores'].get('Liquidity Swept', 0):.2f}",
                f"POI {smc_score['poi_used']}",
                f"Premium/Discount {smc_score['pillar_scores'].get('Premium/Discount Position', 0):.2f}",
                f"Session {smc_score['pillar_scores'].get('Session Timing', 0):.2f}",
            ]
            return {
                "strategy": strategy,
                "strategy_full_name": full_name,
                "smc_score": float(round(smc_score["smc_score"], 2)),
                "pillar_scores": smc_score["pillar_scores"],
                "poi_used": smc_score["poi_used"],
                "liquidity_targeted": float(liq_target),
                "entry": float(entry),
                "stop_loss": float(stop),
                "target_1": float(target_1),
                "target_2": float(target_2),
                "target_3": float(target_3),
                "confluence_factors": confluences,
                "confidence": float(round(smc_score["smc_score"], 2)),
                "description": f"{'SMC Long' if strategy == 'SMC_LONG' else 'SMC Short'}: full 5-pillar confluence at {entry:.2f}, targeting liquidity at {liq_target:.2f}.",
            }
        except Exception as exc:
            logger.exception("generate_smc_signal failed: {}", exc)
            return None
