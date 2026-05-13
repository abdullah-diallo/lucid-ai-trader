"""
ai/probability_engine.py
=========================
Calculates dynamic trade success probability using Groq (LLaMA 3 70B).
Evaluates current market conditions against the signal and historical stats.
Wraps all Groq calls in try/except — returns a safe fallback on any error.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from ai.groq_client import DEFAULT_MODEL, get_groq

logger = logging.getLogger(__name__)

_FALLBACK = {
    "probability_pct":       65,
    "historical_avg_pct":    65,
    "market_condition_label": "Neutral",
    "display_string":        "65% | Historical avg",
    "factors_boosting":      [],
    "factors_reducing":      ["AI analysis unavailable"],
}


class SuccessProbabilityEngine:
    """
    Dynamic success probability assessment for a trade signal.

    Usage:
        engine = SuccessProbabilityEngine()
        prob   = engine.calculate_probability(signal, context, strategy_stats)
        # prob["display_string"] → "74% | Avg: 68% | Today: Favorable"
    """

    def calculate_probability(
        self,
        signal: Dict[str, Any],
        context: Dict[str, Any],
        strategy_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns probability dict.  Never raises — returns _FALLBACK on error.
        """
        try:
            prompt = self._build_prompt(signal, context, strategy_stats)
            client = get_groq()
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional futures trading analyst. "
                            "Respond ONLY with valid JSON matching the schema provided. "
                            "No explanation, no markdown, just the JSON object."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            import re as _re
            raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.MULTILINE)
            raw = _re.sub(r"\s*```$", "", raw, flags=_re.MULTILINE)
            data = json.loads(raw.strip())
            return self._validate_result(data, strategy_stats)
        except Exception:
            logger.exception("SuccessProbabilityEngine: Groq call failed.")
            return {**_FALLBACK, "historical_avg_pct": int(strategy_stats.get("win_rate_pct", 65))}

    # ── Prompt builder ────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        signal: Dict[str, Any],
        context: Dict[str, Any],
        strategy_stats: Dict[str, Any],
    ) -> str:
        hist_wr = strategy_stats.get("win_rate_pct", 65)
        trend   = strategy_stats.get("performance_trend", "STABLE")
        last_10 = strategy_stats.get("last_10_trades", [])
        recent  = f"{sum(last_10)}/{len(last_10)}" if last_10 else "n/a"

        confluences = signal.get("confluence_factors", [])

        return f"""Assess the probability of success for this trade signal.

SIGNAL:
  Strategy: {signal.get("strategy_full_name", signal.get("strategy", "?"))}
  Direction: {"LONG" if str(signal.get("action","")).upper()=="BUY" else "SHORT"}
  Symbol: {signal.get("symbol", "?")}
  Entry: {signal.get("entry", signal.get("price", "?"))}
  Stop: {signal.get("stop_loss", "?")}
  Confidence: {signal.get("confidence", "?")}
  Confluences ({len(confluences)}): {", ".join(str(c) for c in confluences[:8])}

MARKET CONTEXT:
  Session: {context.get("current_session", "?")}
  Is kill zone: {context.get("is_kill_zone", "?")}
  Overall bias: {context.get("overall_bias", "?")}
  VWAP position: {context.get("vwap_position", {}).get("position", "?")}
  Market structure: {context.get("market_structure", {}).get("trend", "?")}
  News proximity: {context.get("is_news_window", False)}

HISTORICAL PERFORMANCE:
  Strategy win rate: {hist_wr}%
  Trend: {trend}
  Recent (last 10): {recent} wins

Respond with ONLY this JSON:
{{
  "probability_pct": <integer 0-100>,
  "historical_avg_pct": {int(hist_wr)},
  "market_condition_label": "<Favorable|Neutral|Unfavorable|High Conviction>",
  "factors_boosting": ["<factor>", ...],
  "factors_reducing": ["<factor>", ...]
}}"""

    # ── Result validation ─────────────────────────────────────────────────────

    def _validate_result(
        self, data: Dict[str, Any], strategy_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        prob      = max(0, min(100, int(data.get("probability_pct", 65))))
        hist_avg  = int(strategy_stats.get("win_rate_pct", data.get("historical_avg_pct", 65)))
        condition = data.get("market_condition_label", "Neutral")
        boosting: List[str] = data.get("factors_boosting", [])
        reducing: List[str] = data.get("factors_reducing", [])

        display = f"{prob}% | Avg: {hist_avg}% | Today: {condition}"

        return {
            "probability_pct":        prob,
            "historical_avg_pct":     hist_avg,
            "market_condition_label": condition,
            "display_string":         display,
            "factors_boosting":       boosting,
            "factors_reducing":       reducing,
        }
