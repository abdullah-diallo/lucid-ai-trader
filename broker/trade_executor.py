"""
broker/trade_executor.py
========================
Subscribes to the event bus and routes TradingView signals to the active broker.
The active broker is managed by broker_registry — switch it from the dashboard.

Signal → Order mapping:
  BUY   → Buy  market order
  SELL  → Sell market order
  CLOSE → Liquidate all open positions for that symbol
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from broker.broker_registry import broker_registry
from data.tradingview_client import InMemoryEventBus

logger = logging.getLogger(__name__)


class TradeExecutor:
    """
    Listens for validated trading signals and routes them to broker_registry.
    Paper mode is now handled by PaperBroker — this class just forwards signals.
    """

    def __init__(self, paper_mode: bool = True, order_qty: int = 1, **_ignored) -> None:
        self.paper_mode = paper_mode
        self.order_qty  = order_qty

    # kept for backward-compat: server.py passes client= keyword
    @classmethod
    def from_env(cls) -> "TradeExecutor":
        paper = os.getenv("PAPER_MODE", "true").lower() == "true"
        qty   = int(os.getenv("ORDER_QTY", "1"))
        return cls(paper_mode=paper, order_qty=qty)

    def initialize(self) -> None:
        mode = "PAPER" if self.paper_mode else "LIVE"
        logger.info("TradeExecutor: %s MODE — active broker: %s", mode, broker_registry.active_name)

    def attach(self, event_bus: InMemoryEventBus) -> None:
        event_bus.subscribe("tradingview.signal", self.on_signal)
        logger.info("TradeExecutor subscribed to tradingview.signal events.")

    # ── Signal handler ────────────────────────────────────────────────────────

    def on_signal(self, payload: Dict[str, Any]) -> None:
        symbol    = str(payload.get("symbol", "")).strip()
        action_tv = str(payload.get("action", "")).strip().upper()
        price     = payload.get("price")
        reason    = payload.get("reason", "")

        logger.info("Signal → action=%s symbol=%s price=%s reason=%s",
                    action_tv, symbol, price, reason)

        if self.paper_mode and broker_registry.active_name not in ("paper",):
            logger.info("[PAPER MODE] Signal received but live trading is disabled. "
                        "Set PAPER_MODE=false in .env to enable live orders.")
            return

        try:
            if action_tv == "CLOSE":
                result = broker_registry.close_position(symbol)
                logger.info("close_position → %s", result)

            elif action_tv == "BUY":
                result = broker_registry.place_order(
                    symbol, self.order_qty, "Buy",
                    price=float(price) if price else None,
                )
                logger.info("place_order Buy → %s", result)

            elif action_tv == "SELL":
                result = broker_registry.place_order(
                    symbol, self.order_qty, "Sell",
                    price=float(price) if price else None,
                )
                logger.info("place_order Sell → %s", result)

            else:
                logger.warning("Unrecognised action '%s' — signal ignored.", action_tv)

        except Exception:
            logger.exception("TradeExecutor: error handling signal action=%s symbol=%s",
                             action_tv, symbol)
