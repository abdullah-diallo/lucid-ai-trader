"""
tradingview_client.py
====================
TradingView webhook receiver and Pine Script generator for lucid-ai-trader.

Why this exists
---------------
TradingView does not expose a direct market data API for alert strategies.
Instead, TradingView sends HTTP webhooks when alert conditions fire.
This module receives those webhooks, validates them, logs them, and emits
normalized signal events to the application's event bus.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"BUY", "SELL", "CLOSE"}


class EventBusProtocol(Protocol):
    """
    Minimal event bus interface expected by the webhook receiver.
    """

    def emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        """
        Emit an event with a JSON-serializable payload.
        """


class InMemoryEventBus:
    """
    Small in-memory event bus used by default for local development.
    In production, replace this with your real bus implementation.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def subscribe(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe a callback to a named event.
        """
        self._handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        """
        Emit to all subscribers. Individual handler failures are isolated so one
        bad handler does not block all other handlers.
        """
        for handler in self._handlers.get(event_name, []):
            try:
                handler(payload)
            except Exception:
                logger.exception("Event handler failed for event '%s'.", event_name)


@dataclass
class TradingViewSignal:
    """
    Normalized representation of a TradingView alert webhook payload.
    """

    symbol: str
    action: str
    price: float
    timeframe: str
    reason: str
    source: str = "tradingview"
    received_at: str = ""


class TradingViewWebhookReceiver:
    """
    Flask-based TradingView webhook receiver.

    Expected request body:
    {
      "symbol": "MES1!",
      "action": "BUY" | "SELL" | "CLOSE",
      "price": 5386.25,
      "timeframe": "15m",
      "reason": "ORB breakout confirmed on TradingView",
      "secret": "your_webhook_secret_key"
    }
    """

    def __init__(
        self,
        webhook_secret: Optional[str] = None,
        event_bus: Optional[EventBusProtocol] = None,
        app: Optional[Flask] = None,
    ) -> None:
        self.webhook_secret = webhook_secret or os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
        self.event_bus = event_bus or InMemoryEventBus()
        self.app = app if app is not None else Flask(__name__)
        self._register_routes()

        if not self.webhook_secret:
            logger.warning(
                "TRADINGVIEW_WEBHOOK_SECRET is not set. "
                "Webhook validation will fail until a secret is configured."
            )

    def _register_routes(self) -> None:
        """
        Register Flask routes for health checks and TradingView webhooks.
        """

        @self.app.get("/health")
        def health() -> Any:
            return jsonify({"status": "ok", "service": "tradingview-webhook-receiver"}), 200

        @self.app.post("/tv-webhook")
        def tv_webhook() -> Any:
            return self._handle_webhook()

    def _handle_webhook(self) -> Any:
        """
        Main webhook handler with full validation and error handling.
        """
        try:
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                logger.warning(
                    "Rejected webhook: invalid JSON payload. remote_addr=%s",
                    request.remote_addr,
                )
                return jsonify({"status": "error", "message": "Invalid JSON payload."}), 400

            # Log webhook without leaking secret content.
            safe_payload = dict(payload)
            if "secret" in safe_payload:
                safe_payload["secret"] = "***REDACTED***"
            logger.info("Incoming TradingView webhook: %s", json.dumps(safe_payload, sort_keys=True))

            error = self._validate_payload(payload)
            if error:
                logger.warning("Rejected webhook: %s", error)
                return jsonify({"status": "error", "message": error}), 400

            if not self._is_secret_valid(str(payload["secret"])):
                logger.warning("Rejected webhook: secret mismatch for symbol=%s", payload.get("symbol"))
                return jsonify({"status": "error", "message": "Invalid secret."}), 403

            signal = TradingViewSignal(
                symbol=str(payload["symbol"]).strip(),
                action=str(payload["action"]).strip().upper(),
                price=float(payload["price"]),
                timeframe=str(payload["timeframe"]).strip(),
                reason=str(payload["reason"]).strip(),
                received_at=datetime.now(timezone.utc).isoformat(),
            )
            signal_payload = asdict(signal)

            self.event_bus.emit("tradingview.signal", signal_payload)
            logger.info(
                "TradingView signal emitted to event bus. symbol=%s action=%s price=%.4f timeframe=%s",
                signal.symbol,
                signal.action,
                signal.price,
                signal.timeframe,
            )

            return jsonify({"status": "ok", "signal": signal_payload}), 200
        except Exception:
            logger.exception("Unhandled exception while processing TradingView webhook.")
            return jsonify({"status": "error", "message": "Internal server error."}), 500

    def _validate_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Validate required fields and semantic value constraints.
        """
        required_keys = {"symbol", "action", "price", "timeframe", "reason", "secret"}
        missing = sorted(required_keys - payload.keys())
        if missing:
            return f"Missing required field(s): {', '.join(missing)}"

        action = str(payload["action"]).strip().upper()
        if action not in VALID_ACTIONS:
            return "Field 'action' must be one of BUY, SELL, CLOSE."

        try:
            price = float(payload["price"])
            if price <= 0:
                return "Field 'price' must be a positive number."
        except (TypeError, ValueError):
            return "Field 'price' must be numeric."

        for key in ("symbol", "timeframe", "reason", "secret"):
            value = str(payload[key]).strip()
            if not value:
                return f"Field '{key}' cannot be empty."

        return None

    def _is_secret_valid(self, incoming_secret: str) -> bool:
        """
        Constant-time secret comparison to avoid timing attacks.
        """
        if not self.webhook_secret:
            return False
        return hmac.compare_digest(incoming_secret.strip(), self.webhook_secret)

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        debug: bool = False,
    ) -> None:
        """
        Start the Flask webhook server.
        """
        logger.info("Starting TradingView webhook receiver on %s:%s", host, port)
        self.app.run(host=host, port=port, debug=debug)

    @staticmethod
    def generate_pine_script(
        webhook_secret: str = "{{TRADINGVIEW_WEBHOOK_SECRET}}",
        default_symbol_hint: str = "MES1!",
    ) -> str:
        """
        Generate a ready-to-use Pine Script v5 strategy helper.

        Notes:
        - Use this on a 5-minute chart.
        - Works for MES1! and MNQ1! if applied to those symbols.
        - In TradingView Alert settings, choose "Any alert() function call",
          then set your webhook URL to your /tv-webhook endpoint.
        """
        escaped_secret = webhook_secret.replace('"', '\\"')
        escaped_symbol_hint = default_symbol_hint.replace('"', '\\"')
        return f"""//@version=5
indicator("Lucid ORB + FVG + OB Webhook Helper", overlay=true, max_boxes_count=300, max_labels_count=300)

// =============================================================================
// SECTION 1: USER SETTINGS
// -----------------------------------------------------------------------------
// This script is designed for 5-minute MES1! and MNQ1! charts.
// It can run on other symbols, but ORB sizing assumptions are tuned for index
// futures behavior around the US session open.
// =============================================================================
sessionRTH = input.session("0930-1600", "RTH Session (US/Eastern)")
orbMinutes = input.int(15, "ORB minutes", minval=5, maxval=60)
fvgLookback = input.int(100, "FVG lookback bars", minval=20, maxval=500)
obLookback = input.int(100, "Order Block lookback bars", minval=20, maxval=500)
webhookSecret = input.string("{escaped_secret}", "Webhook Secret")
symbolOverride = input.string("{escaped_symbol_hint}", "Symbol override (blank=chart symbol)")

// =============================================================================
// SECTION 2: SESSION / ORB DETECTION
// -----------------------------------------------------------------------------
// ORB (Opening Range Breakout):
// - We define opening range as first 15 minutes of RTH (09:30 - 09:45 ET).
// - On a 5-minute chart this is the first 3 bars.
// =============================================================================
inRTH = not na(time(timeframe.period, sessionRTH))
newRTH = inRTH and not inRTH[1]
barsSinceRTHOpen = ta.barssince(newRTH)
inORBWindow = inRTH and barsSinceRTHOpen >= 0 and barsSinceRTHOpen < math.floor(orbMinutes / 5)

var float orbHigh = na
var float orbLow = na
var bool orbLocked = false

if newRTH
    orbHigh := high
    orbLow := low
    orbLocked := false
else if inORBWindow
    orbHigh := na(orbHigh) ? high : math.max(orbHigh, high)
    orbLow := na(orbLow) ? low : math.min(orbLow, low)
else if inRTH and not orbLocked and barsSinceRTHOpen >= math.floor(orbMinutes / 5)
    orbLocked := true

// Draw ORB levels.
plot(orbHigh, "ORB High", color=color.new(color.green, 0), linewidth=2, style=plot.style_linebr)
plot(orbLow, "ORB Low", color=color.new(color.red, 0), linewidth=2, style=plot.style_linebr)

// =============================================================================
// SECTION 3: FAIR VALUE GAP (FVG) DETECTION
// -----------------------------------------------------------------------------
// Simple 3-candle imbalance definition:
// - Bullish FVG when low > high[2]
// - Bearish FVG when high < low[2]
// We draw each detected zone as a shaded box extending right.
// =============================================================================
bullishFVG = low > high[2]
bearishFVG = high < low[2]

var box[] fvgBoxes = array.new_box()
var float lastBullFVGTop = na
var float lastBullFVGBottom = na
var float lastBearFVGTop = na
var float lastBearFVGBottom = na

if bullishFVG and bar_index > 2 and bar_index > bar_index - fvgLookback
    top = low
    bottom = high[2]
    lastBullFVGTop := top
    lastBullFVGBottom := bottom
    fvgBox = box.new(left=bar_index - 2, top=top, right=bar_index + 20, bottom=bottom, bgcolor=color.new(color.teal, 84), border_color=color.new(color.teal, 20))
    array.push(fvgBoxes, fvgBox)

if bearishFVG and bar_index > 2 and bar_index > bar_index - fvgLookback
    top = low[2]
    bottom = high
    lastBearFVGTop := top
    lastBearFVGBottom := bottom
    fvgBox = box.new(left=bar_index - 2, top=top, right=bar_index + 20, bottom=bottom, bgcolor=color.new(color.orange, 84), border_color=color.new(color.orange, 20))
    array.push(fvgBoxes, fvgBox)

// =============================================================================
// SECTION 4: ORDER BLOCK (OB) APPROXIMATION
// -----------------------------------------------------------------------------
// Simplified OB logic for visual context:
// - Bullish OB candidate: last bearish candle before strong bullish impulse.
// - Bearish OB candidate: last bullish candle before strong bearish impulse.
// This is a practical approximation, not a full institutional engine.
// =============================================================================
impulseUp = close > high[1] and close > open and (close - open) > ta.atr(14) * 0.5
impulseDown = close < low[1] and close < open and (open - close) > ta.atr(14) * 0.5

var box[] obBoxes = array.new_box()
var float lastBullOBTop = na
var float lastBullOBBottom = na
var float lastBearOBTop = na
var float lastBearOBBottom = na

if impulseUp and close[1] < open[1] and bar_index > obLookback
    // Bullish OB is previous bearish candle range.
    lastBullOBTop := high[1]
    lastBullOBBottom := low[1]
    obBox = box.new(left=bar_index - 1, top=high[1], right=bar_index + 30, bottom=low[1], bgcolor=color.new(color.lime, 88), border_color=color.new(color.lime, 28))
    array.push(obBoxes, obBox)

if impulseDown and close[1] > open[1] and bar_index > obLookback
    // Bearish OB is previous bullish candle range.
    lastBearOBTop := high[1]
    lastBearOBBottom := low[1]
    obBox = box.new(left=bar_index - 1, top=high[1], right=bar_index + 30, bottom=low[1], bgcolor=color.new(color.red, 88), border_color=color.new(color.red, 28))
    array.push(obBoxes, obBox)

// =============================================================================
// SECTION 5: ORB / ZONE EVENTS
// -----------------------------------------------------------------------------
// We detect:
// 1) ORB breakouts above/below range.
// 2) Price entering a recent FVG zone.
// 3) Price entering a recent Order Block zone.
// =============================================================================
orbBreakUp = orbLocked and ta.crossover(close, orbHigh)
orbBreakDown = orbLocked and ta.crossunder(close, orbLow)

inBullFVG = not na(lastBullFVGTop) and close <= lastBullFVGTop and close >= lastBullFVGBottom
inBearFVG = not na(lastBearFVGTop) and close <= lastBearFVGTop and close >= lastBearFVGBottom

inBullOB = not na(lastBullOBTop) and close <= lastBullOBTop and close >= lastBullOBBottom
inBearOB = not na(lastBearOBTop) and close <= lastBearOBTop and close >= lastBearOBBottom

plotshape(orbBreakUp, title="ORB Break Up", style=shape.triangleup, location=location.belowbar, color=color.new(color.green, 0), size=size.tiny, text="ORB↑")
plotshape(orbBreakDown, title="ORB Break Down", style=shape.triangledown, location=location.abovebar, color=color.new(color.red, 0), size=size.tiny, text="ORB↓")

// =============================================================================
// SECTION 6: WEBHOOK ALERT PAYLOADS
// -----------------------------------------------------------------------------
// TradingView sends these JSON messages via alert() calls.
// Configure one alert in TradingView:
//   Condition: Any alert() function call
//   Webhook URL: https://YOUR_SERVER/tv-webhook
// =============================================================================
sym = str.length(symbolOverride) > 0 ? symbolOverride : syminfo.ticker
tf = timeframe.period

buildPayload(action, reasonText) =>
    "{{" +
    "\\"symbol\\":\\"" + sym + "\\"," +
    "\\"action\\":\\"" + action + "\\"," +
    "\\"price\\":" + str.tostring(close) + "," +
    "\\"timeframe\\":\\"" + tf + "\\"," +
    "\\"reason\\":\\"" + reasonText + "\\"," +
    "\\"secret\\":\\"" + webhookSecret + "\\"" +
    "}}"

if orbBreakUp
    alert(buildPayload("BUY", "ORB breakout confirmed on TradingView"), alert.freq_once_per_bar_close)

if orbBreakDown
    alert(buildPayload("SELL", "ORB breakdown confirmed on TradingView"), alert.freq_once_per_bar_close)

if inBullFVG or inBearFVG
    alert(buildPayload("CLOSE", "Price entered an FVG zone"), alert.freq_once_per_bar_close)

if inBullOB or inBearOB
    alert(buildPayload("CLOSE", "Price entered an Order Block zone"), alert.freq_once_per_bar_close)
"""


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    receiver = TradingViewWebhookReceiver()
    receiver.run()
