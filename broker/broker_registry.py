"""
broker/broker_registry.py
=========================
Central registry — one active broker at a time, switchable from the dashboard.
Paper trading is always available and starts as the default.
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Dict, List, Optional

from broker.base_broker import BaseBroker, OrderResult, Position
from broker.paper_broker import PaperBroker
from broker.tradovate_broker import TradovateBroker
from broker.ibkr_broker import IBKRBroker

logger = logging.getLogger(__name__)

# Every supported broker, in display order
_ALL_BROKERS: Dict[str, type] = {
    "paper":    PaperBroker,
    "tradovate": TradovateBroker,
    "ibkr":     IBKRBroker,
}


class BrokerRegistry:
    """
    Holds one instance of each broker that has been connected.
    The dashboard calls connect() / switch_to() / disconnect().
    TradeExecutor calls place_order() / close_position() on the active broker.
    """

    def __init__(self) -> None:
        self._instances: Dict[str, BaseBroker] = {}
        self._active_name: str = "paper"
        self._lock = Lock()

        # Paper broker is always pre-connected
        paper = PaperBroker()
        paper.connect(starting_balance=100_000.0)
        self._instances["paper"] = paper
        logger.info("BrokerRegistry ready. Default: built-in paper trading.")

    # ── Active broker ─────────────────────────────────────────────────────────

    @property
    def active(self) -> BaseBroker:
        return self._instances.get(self._active_name, self._instances["paper"])

    @property
    def active_name(self) -> str:
        return self._active_name

    # ── Dashboard API ─────────────────────────────────────────────────────────

    def list_all(self) -> List[Dict[str, Any]]:
        """Return status of all brokers (connected or not) for the UI."""
        result = []
        for name, cls in _ALL_BROKERS.items():
            inst = self._instances.get(name)
            if inst:
                d = inst.status_dict()
            else:
                proto = cls()
                d = {
                    "name":              proto.name,
                    "display_name":      proto.display_name,
                    "connected":         False,
                    "supports_futures":  proto.supports_futures,
                    "supports_forex":    proto.supports_forex,
                    "supports_stocks":   proto.supports_stocks,
                    "supports_crypto":   proto.supports_crypto,
                }
            d["is_active"]         = (name == self._active_name)
            d["connection_fields"] = (inst or proto).get_connection_fields()
            result.append(d)
        return result

    def connect(self, broker_name: str, **credentials) -> tuple[bool, str]:
        """Create (or reconnect) a broker and make it active."""
        with self._lock:
            if broker_name not in _ALL_BROKERS:
                return False, f"Unknown broker: '{broker_name}'"
            if broker_name not in self._instances:
                self._instances[broker_name] = _ALL_BROKERS[broker_name]()
            ok, msg = self._instances[broker_name].connect(**credentials)
            if ok:
                self._active_name = broker_name
                logger.info("Active broker → %s", broker_name)
            return ok, msg

    def switch_to(self, broker_name: str) -> tuple[bool, str]:
        """Switch active broker (must already be connected)."""
        with self._lock:
            inst = self._instances.get(broker_name)
            if not inst or not inst.is_connected():
                return False, f"'{broker_name}' is not connected. Connect it first."
            self._active_name = broker_name
            logger.info("Switched active broker to %s", broker_name)
            return True, f"Now using {inst.display_name}"

    def disconnect(self, broker_name: str) -> None:
        with self._lock:
            inst = self._instances.get(broker_name)
            if inst:
                inst.disconnect()
            if self._active_name == broker_name:
                self._active_name = "paper"
                logger.info("Fell back to paper trading after disconnecting %s", broker_name)

    # ── Trading passthrough ───────────────────────────────────────────────────

    def place_order(
        self, symbol: str, qty: int, side: str,
        price: Optional[float] = None,
    ) -> OrderResult:
        return self.active.place_order(symbol, qty, side, price=price)

    def close_position(self, symbol: str) -> OrderResult:
        return self.active.close_position(symbol)

    def get_positions(self) -> List[Position]:
        return self.active.get_positions()

    def get_balance(self) -> float:
        return self.active.get_account_balance()


# Module-level singleton — import this everywhere
broker_registry = BrokerRegistry()
