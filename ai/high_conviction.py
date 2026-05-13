"""
ai/high_conviction.py
======================
Detects trade setups that are exceptional enough to warrant an override
of a normally-blocking rule (e.g., confidence threshold, time filter).

A HIGH CONVICTION OVERRIDE fires when ALL of the following are true:
  1. signal confidence ≥ 0.88
  2. ≥ 4 confluence factors present
  3. The blocking rule is NOT a hard risk limit (halt_level < 4)
  4. Account is not at max drawdown risk

For PROTECTED accounts: the override alert is sent but no trade is entered.
For non-PROTECTED accounts: if the 90-second window expires without response,
the trade is entered with 1 contract.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE    = 0.88
_MIN_CONFLUENCES   = 4
_SMC_PILLAR_KEYS   = [
    "Higher Timeframe Bias",
    "Liquidity Swept",
    "Point of Interest Quality",
    "Premium/Discount Position",
    "Session Timing",
]


class HighConvictionChecker:
    """
    Checks whether a skipped/timed-out signal qualifies for an override request.

    Usage:
        checker = HighConvictionChecker(risk_manager)
        override = checker.check_high_conviction_override(signal, context, account)
        if override:
            telegram_bot.send_override_request(signal, override)
    """

    def __init__(self, risk_manager) -> None:
        self._risk_manager = risk_manager

    def check_high_conviction_override(
        self,
        signal: Dict[str, Any],
        context: Dict[str, Any],
        account: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Returns override_details dict if criteria are met, else None.
        """
        if not signal or not account:
            return None

        confidence = float(signal.get("confidence", 0))
        if confidence < _MIN_CONFIDENCE:
            return None

        confluences = signal.get("confluence_factors", [])
        if len(confluences) < _MIN_CONFLUENCES:
            return None

        # Do not fire when account is at a hard halt (L4 or L5)
        risk_status = self._risk_manager.get_risk_status(account)
        if risk_status.get("halt_level", 0) >= 4:
            return None

        # Do not fire when drawdown is within 1% of the limit (near-breach)
        drawdown_pct = risk_status.get("drawdown_pct", 0)
        max_dd_pct   = risk_status.get("max_drawdown_pct", 5.0)
        if drawdown_pct >= max_dd_pct * 0.90:
            return None

        # Count SMC pillars from pillar_scores if available
        pillar_score_count = self._count_smc_pillars(signal, context)

        # Build override details
        direction = "LONG" if str(signal.get("action", "")).upper() == "BUY" else "SHORT"
        strategy  = signal.get("strategy_full_name", signal.get("strategy", "?"))

        good_parts = []
        if confidence >= 0.90:
            good_parts.append(f"{confidence*100:.0f}% confidence")
        if len(confluences) >= 5:
            good_parts.append(f"{len(confluences)} confluences align")
        if pillar_score_count >= 4:
            good_parts.append(f"{pillar_score_count}/5 SMC pillars pass")
        good_parts += [str(c) for c in confluences[:3]]

        return {
            "why_blocked":          "See signal routing log",  # caller fills this in
            "why_still_good":       ", ".join(good_parts),
            "recommended_contracts": 1,
            "confidence":           confidence,
            "confluence_count":     len(confluences),
            "smc_pillar_count":     pillar_score_count,
            "strategy":             strategy,
            "direction":            direction,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _count_smc_pillars(
        self, signal: Dict[str, Any], context: Dict[str, Any]
    ) -> int:
        """
        Count how many of the 5 SMC pillars are present.
        Uses explicit pillar_scores if available, otherwise infers from context/signal.
        """
        pillar_scores = signal.get("pillar_scores", {})
        if pillar_scores:
            # Count pillars that meet their minimum score
            thresholds = {
                "Higher Timeframe Bias":       0.70,
                "Liquidity Swept":             0.50,
                "Point of Interest Quality":   0.60,
                "Premium/Discount Position":   0.50,
                "Session Timing":              0.50,
            }
            return sum(
                1 for key, min_score in thresholds.items()
                if float(pillar_scores.get(key, 0)) >= min_score
            )

        # Infer from context when explicit scores absent
        count = 0

        # Pillar 1: HTF bias alignment
        bias = str(context.get("overall_bias", "")).upper()
        action = str(signal.get("action", "")).upper()
        if (bias == "BULLISH" and action == "BUY") or (bias == "BEARISH" and action == "SELL"):
            count += 1

        # Pillar 2: Liquidity swept
        confluences = signal.get("confluence_factors", [])
        conf_text = " ".join(str(c).lower() for c in confluences)
        if "liquidity" in conf_text or "sweep" in conf_text or "ssl" in conf_text or "bsl" in conf_text:
            count += 1

        # Pillar 3: POI at entry (OB or FVG)
        if "order block" in conf_text or "fvg" in conf_text or "fair value" in conf_text:
            count += 1

        # Pillar 4: BOS/CHoCH confirmation
        if "bos" in conf_text or "choch" in conf_text or "break of structure" in conf_text:
            count += 1

        # Pillar 5: Session timing (kill zone)
        is_kill_zone = context.get("is_kill_zone", False)
        session      = str(context.get("current_session", "")).upper()
        if is_kill_zone or "kill" in conf_text or session in ("NY_OPEN", "LONDON", "NY_AM"):
            count += 1

        return count
