"""
broker/base_broker.py
=====================
Abstract interface every broker adapter must implement.
TradeExecutor talks only to this — never to broker-specific code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OrderResult:
    order_id: str
    status: str          # "filled" | "pending" | "rejected" | "error" | "no_position"
    symbol: str
    side: str            # "Buy" | "Sell" | ""
    qty: int
    fill_price: Optional[float] = None
    message: str = ""


@dataclass
class Position:
    symbol: str
    qty: int             # positive = long, negative = short
    avg_price: float
    unrealized_pnl: float = 0.0
    side: str = "Long"


class BaseBroker(ABC):
    name: str = "base"
    display_name: str = "Base Broker"
    supports_futures: bool = False
    supports_forex: bool = False
    supports_stocks: bool = False
    supports_crypto: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self, **credentials) -> tuple[bool, str]:
        """Connect with the provided credentials. Returns (success, message)."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly disconnect."""

    @abstractmethod
    def is_connected(self) -> bool:
        """True if currently authenticated and ready."""

    # ── Trading ───────────────────────────────────────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order. side is 'Buy' or 'Sell'."""

    @abstractmethod
    def close_position(self, symbol: str) -> OrderResult:
        """Liquidate all open positions for a symbol."""

    # ── Account ───────────────────────────────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open positions."""

    @abstractmethod
    def get_account_balance(self) -> float:
        """Return current cash / net liquidation value."""

    # ── UI metadata ───────────────────────────────────────────────────────────

    @abstractmethod
    def get_connection_fields(self) -> List[Dict[str, str]]:
        """
        Fields the dashboard shows on the connect form.
        Each dict: {"name": str, "label": str, "type": "text"|"password"|"number", "default": str}
        """

    def status_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "connected": self.is_connected(),
            "supports_futures": self.supports_futures,
            "supports_forex": self.supports_forex,
            "supports_stocks": self.supports_stocks,
            "supports_crypto": self.supports_crypto,
        }
