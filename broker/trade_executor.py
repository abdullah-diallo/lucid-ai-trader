"""
broker/trade_executor.py
========================
Subscribes to the event bus and routes TradingView signals to Tradovate orders.

Signal → Order mapping:
  BUY   → Buy  market order
  SELL  → Sell market order
  CLOSE → Liquidate all open positions for that symbol

In PAPER_MODE=true, all orders are logged but never sent to Tradovate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from broker.tradovate_client import TradovateClient
from data.tradingview_client import InMemoryEventBus

logger = logging.getLogger(__name__)

_TV_TO_TRADOVATE = {"BUY": "Buy", "SELL": "Sell"}


def _normalize_symbol(tv_symbol: str) -> str:
    """
    Convert a TradingView continuous-contract symbol to Tradovate format.
    MES1!  → @MES
    NQ1!   → @NQ
    ES1!   → @ES
    Already-clean symbols pass through unchanged.
    """
    sym = tv_symbol.strip()
    # Strip trailing "1!" or "!" (TradingView continuous contract suffix)
    if sym.endswith("1!"):
        sym = sym[:-2]
    elif sym.endswith("!"):
        sym = sym[:-1]
    # Prepend "@" for Tradovate continuous contract notation
    if not sym.startswith("@"):
        sym = f"@{sym}"
    return sym


class TradeExecutor:
    """
    Listens for validated trading signals and executes them via Tradovate.

    Usage:
        executor = TradeExecutor(client, paper_mode=True)
        executor.initialize()       # fetches account details
        executor.attach(event_bus)  # subscribes to "tradingview.signal"
    """

    def __init__(
        self,
        client: TradovateClient,
        paper_mode: bool = True,
        order_qty: int = 1,
    ) -> None:
        self.client = client
        self.paper_mode = paper_mode
        self.order_qty = order_qty
        self._account_id: Optional[int] = None
        self._account_spec: Optional[str] = None

    def initialize(self) -> None:
        """
        Authenticate and cache account details.
        Call once at startup before attaching to the event bus.
        """
        if self.paper_mode:
            logger.info("TradeExecutor: PAPER MODE active — no live orders will be placed.")
            return
        accounts = self.client.get_accounts()
        if not accounts:
            raise RuntimeError("No Tradovate accounts found. Check credentials in .env.")
        acct = accounts[0]
        self._account_id = int(acct["id"])
        self._account_spec = str(acct.get("name", self._account_id))
        logger.info(
            "TradeExecutor ready. Account: %s (id=%s).",
            self._account_spec, self._account_id,
        )

    def attach(self, event_bus: InMemoryEventBus) -> None:
        event_bus.subscribe("tradingview.signal", self.on_signal)
        logger.info("TradeExecutor subscribed to tradingview.signal events.")

    # ── Signal handler ────────────────────────────────────────────────────────

    def on_signal(self, payload: Dict[str, Any]) -> None:
        symbol_tv = str(payload.get("symbol", "")).strip()
        action_tv = str(payload.get("action", "")).strip().upper()
        price = payload.get("price")
        reason = payload.get("reason", "")

        logger.info(
            "Signal → action=%s symbol=%s price=%s reason=%s",
            action_tv, symbol_tv, price, reason,
        )

        if action_tv == "CLOSE":
            self._handle_close(symbol_tv)
        elif action_tv in _TV_TO_TRADOVATE:
            self._handle_order(symbol_tv, action_tv)
        else:
            logger.warning("Unrecognised action '%s' — signal ignored.", action_tv)

    # ── Order execution ───────────────────────────────────────────────────────

    def _handle_order(self, symbol_tv: str, action_tv: str) -> None:
        symbol = _normalize_symbol(symbol_tv)
        action = _TV_TO_TRADOVATE[action_tv]

        if self.paper_mode:
            logger.info("[PAPER] %s %s x%s @ market.", action, symbol, self.order_qty)
            return

        if self._account_id is None:
            logger.error("Account not initialised — cannot place order.")
            return

        try:
            result = self.client.place_order(
                account_id=self._account_id,
                account_spec=self._account_spec,
                symbol=symbol,
                action=action,
                qty=self.order_qty,
            )
            logger.info("Order placed: %s", result)
        except Exception:
            logger.exception("Failed to place %s order for %s.", action, symbol)

    def _handle_close(self, symbol_tv: str) -> None:
        if self.paper_mode:
            logger.info("[PAPER] Would liquidate all positions for %s.", symbol_tv)
            return

        if self._account_id is None:
            logger.error("Account not initialised — cannot liquidate.")
            return

        try:
            positions = self.client.get_positions()
            if not positions:
                logger.info("No open positions to close.")
                return
            for pos in positions:
                pos_id = pos.get("id")
                if pos_id is not None:
                    result = self.client.liquidate_position(int(pos_id))
                    logger.info("Liquidated position id=%s: %s", pos_id, result)
        except Exception:
            logger.exception("Failed to liquidate positions for %s.", symbol_tv)
