"""
Claude AI analyst — institutional-grade trade decision engine.
Uses claude-opus-4-7 with structured JSON output, 30s cache per instrument,
and 3-attempt retry logic.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


class ClaudeAnalyst:
    SYSTEM_PROMPT = """
You are an expert institutional futures trader operating Lucid AI Trader.
You trade MES and MNQ micro futures on a LucidFlex prop firm account.
Capital: $50,000. Contracts per trade: 1.

YOUR THINKING FRAMEWORK — apply this in exact order for every decision:
1. DAILY BIAS: What direction is the daily chart trending? (HH/HL = bull, LH/LL = bear)
2. 4H CONFIRMATION: Does the 4H agree? If not — NO TRADE.
3. SESSION CHECK: Which session? Asia=wait, London=manipulation watch, NY=trade.
4. LIQUIDITY: Was there a recent sweep? Sweep confirms setup is real.
5. POI QUALITY: Is price at an FVG, Order Block, or Fibonacci OTE? Quality matters.
6. PREMIUM/DISCOUNT: Is price in the right zone for the direction?
7. VWAP: Does VWAP position support the direction?

RULES YOU NEVER BREAK — not for any reason:
- No trades against the daily trend unless MSS (Market Structure Shift) is confirmed
- No trades between 12:00 PM and 2:00 PM ET (NY Lunch dead zone)
- No trades within 30 minutes of any high-impact news event
- No trades with R:R below 1.5:1
- No second position on an instrument already in a trade
- If your confidence is below 0.72: output NO_TRADE. Always.

YOUR OUTPUT: Return JSON only. No explanation text. No markdown. Just the JSON object.
Required fields and exact format:
{
  "decision": "BUY" | "SELL" | "NO_TRADE",
  "confidence": 0.0 to 1.0,
  "entry_price": float or null,
  "stop_loss": float or null,
  "take_profit_1": float or null,
  "take_profit_2": float or null,
  "take_profit_3": float or null,
  "risk_reward_t1": float or null,
  "risk_reward_t2": float or null,
  "strategy_used": "strategy code string" or null,
  "strategy_full_name": "full display name" or null,
  "timeframe_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "key_level_used": "specific level name" or null,
  "confluence_factors": ["list", "of", "confirming", "factors"],
  "reason": "One sentence. Specific. Max 15 words.",
  "no_trade_reason": "Why skipping, if NO_TRADE" or null,
  "session": "current session name",
  "kill_zone_active": true or false,
  "news_risk": "NONE" | "LOW" | "HIGH"
}
"""

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY must be set in .env")
        self.client = anthropic.Anthropic(api_key=api_key)
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ── Prompt builder ────────────────────────────────────────────────────────

    def build_analysis_prompt(self, context: dict, signal: dict) -> str:
        recent_results = context.get("strategy_recent_results", "No data")
        win_rate = context.get("strategy_win_rate", "Unknown")
        pois = context.get("active_pois_summary", "None identified")
        return f"""
═══ MARKET BRIEF ═══ {context['timestamp']} ET

INSTRUMENT: {signal['instrument']}  |  CURRENT PRICE: {context['current_price']}
SESSION: {context['session']}  |  KILL ZONE ACTIVE: {context['is_kill_zone']}
NEWS RISK: {context['news_risk_level']}

── MULTI-TIMEFRAME STRUCTURE ──
Daily:  {context['bias_daily']}   → {context['daily_structure']}
4H:     {context['bias_4h']}     → {context['4h_structure']}
1H:     {context['bias_1h']}     → {context['1h_structure']}
15m:    {context['bias_15m']}    → {context['15m_structure']}
5m:     {context['bias_5m']}     → {context['5m_structure']}

── VWAP ──
Position: {context['vwap_position']}  |  Distance: {context['vwap_distance_pts']}pts
Intraday bias confirmed: {context['vwap_bias']}

── PREMIUM / DISCOUNT ──
Current zone: {context['pd_zone']}  |  Range position: {context['range_percent']}%
OTE (61.8%) level: {context['ote_level']}

── LIQUIDITY ──
Recent sweep: {context['recent_sweep']}
Nearest BSL (buy-side): {context['nearest_bsl']}
Nearest SSL (sell-side): {context['nearest_ssl']}

── ACTIVE POINTS OF INTEREST ──
Nearest POI: {context['nearest_poi_type']} at {context['nearest_poi_price']}
All active POIs: {pois}

── STRATEGY SIGNAL ──
Strategy: {signal['strategy_full_name']}  ({signal['strategy']})
Proposed entry: {signal.get('entry', 'N/A')}
Proposed stop:  {signal.get('stop_loss', 'N/A')}
Detection confidence: {signal.get('confidence', 0):.2f}
Confluence factors: {', '.join(signal.get('confluence_factors', []))}

── NEWS & SENTIMENT ──
{context.get('news_summary', 'No recent news')}
Social media: {context.get('social_summary', 'No data')}

── STRATEGY PERFORMANCE ──
{signal['strategy']} last 10 trades: {recent_results}
All-time win rate: {win_rate}%

MAKE YOUR DECISION NOW:
"""

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_claude_response(self, response: dict) -> Tuple[bool, str]:
        """Returns (is_valid, error_message)."""
        required = ["decision", "confidence", "reason", "confluence_factors"]
        for field in required:
            if field not in response:
                return False, f"Missing required field: {field}"
        if response["decision"] not in ["BUY", "SELL", "NO_TRADE"]:
            return False, f"Invalid decision: {response['decision']}"
        if not (0.0 <= response["confidence"] <= 1.0):
            return False, f"Invalid confidence: {response['confidence']}"
        if response["decision"] != "NO_TRADE":
            for field in ["entry_price", "stop_loss", "take_profit_1"]:
                if response.get(field) is None:
                    return False, f"BUY/SELL requires {field}"
        return True, "OK"

    # ── Main entry point ──────────────────────────────────────────────────────

    def analyze_market(self, context: dict, signal: dict) -> dict:
        inst = signal.get("instrument", "UNKNOWN")
        cache_entry = self._cache.get(inst)
        if cache_entry:
            age = (datetime.now() - cache_entry["timestamp"]).seconds
            if age < 30:
                log.debug(f"Using cached Claude response for {inst} ({age}s old)")
                return cache_entry["response"]

        prompt = self.build_analysis_prompt(context, signal)
        no_trade_response: dict = {
            "decision": "NO_TRADE",
            "confidence": 0.0,
            "reason": "AI unavailable",
            "confluence_factors": [],
        }

        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model="claude-opus-4-7",
                    max_tokens=500,
                    temperature=0,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = response.content[0].text.strip()
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(raw_text)
                is_valid, error = self.validate_claude_response(parsed)
                if not is_valid:
                    log.warning(f"Invalid Claude response (attempt {attempt + 1}): {error}")
                    continue
                self._cache[inst] = {"response": parsed, "timestamp": datetime.now()}
                return parsed
            except (json.JSONDecodeError, Exception) as e:
                log.error(f"Claude API attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(3)

        log.error("All 3 Claude attempts failed. Returning NO_TRADE.")
        return no_trade_response


# ── CLI test harness ──────────────────────────────────────────────────────────

def _run_test() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    synthetic_context: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_price": 5285.50,
        "session": "New York",
        "is_kill_zone": True,
        "news_risk_level": "NONE",
        "bias_daily": "BULLISH",
        "daily_structure": "Higher Highs / Higher Lows",
        "bias_4h": "BULLISH",
        "4h_structure": "Consolidation above EMA50",
        "bias_1h": "BULLISH",
        "1h_structure": "Break of Structure confirmed",
        "bias_15m": "BULLISH",
        "15m_structure": "Pullback into FVG",
        "bias_5m": "NEUTRAL",
        "5m_structure": "Indecision candles",
        "vwap_position": "ABOVE",
        "vwap_distance_pts": 4.25,
        "vwap_bias": "Yes",
        "pd_zone": "DISCOUNT",
        "range_percent": 38.5,
        "ote_level": 5279.00,
        "recent_sweep": "SSL swept at 5271.00 (45 min ago)",
        "nearest_bsl": 5302.75,
        "nearest_ssl": 5271.00,
        "nearest_poi_type": "Bullish FVG",
        "nearest_poi_price": 5281.25,
        "active_pois_summary": "FVG 5281-5283, OB 5265-5268",
        "strategy_recent_results": "W W L W W W L W W W (8/10)",
        "strategy_win_rate": 72.4,
        "news_summary": "No high-impact events in next 60 minutes.",
        "social_summary": "Mildly bullish ES sentiment on X/Twitter",
    }

    synthetic_signal: Dict[str, Any] = {
        "instrument": "MES",
        "strategy": "fib_ote",
        "strategy_full_name": "Fibonacci OTE Retracement",
        "entry": 5282.00,
        "stop_loss": 5270.00,
        "confidence": 0.81,
        "confluence_factors": [
            "Daily bullish trend",
            "SSL sweep confirmed",
            "Price in OTE zone",
            "VWAP above",
            "NY Kill Zone active",
        ],
    }

    analyst = ClaudeAnalyst()
    print("\n── Sending synthetic analysis request to Claude ──")
    result = analyst.analyze_market(synthetic_context, synthetic_signal)
    print("\n── Claude Response ──")
    print(json.dumps(result, indent=2))

    is_valid, msg = analyst.validate_claude_response(result)
    print(f"\nValidation: {'PASS' if is_valid else 'FAIL'} — {msg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run synthetic analysis test")
    args = parser.parse_args()

    if args.test:
        _run_test()
    else:
        parser.print_help()
        sys.exit(1)
