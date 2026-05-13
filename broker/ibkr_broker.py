"""
broker/ibkr_broker.py
=====================
Interactive Brokers adapter via ib_insync.
Supports futures, forex, stocks, options — basically any market IBKR offers.

Setup (one-time):
  1. Open a free IBKR account at interactivebrokers.com (paper trading available)
  2. Download and install TWS or IB Gateway from their site
  3. In TWS: Edit → Global Configuration → API → Settings
       ✓ Enable ActiveX and Socket Clients
       ✓ Allow connections from localhost only
       Socket port: 7497 (paper) or 7496 (live)
  4. pip install ib_insync

Paper port: 7497  |  Live port: 7496
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from broker.base_broker import BaseBroker, OrderResult, Position

logger = logging.getLogger(__name__)

# TradingView → IBKR futures contract specs
_FUTURES_MAP: Dict[str, tuple[str, str, str]] = {
    "MES":  ("MES",  "CME",   "USD"),
    "ES":   ("ES",   "CME",   "USD"),
    "MNQ":  ("MNQ",  "CME",   "USD"),
    "NQ":   ("NQ",   "CME",   "USD"),
    "RTY":  ("RTY",  "CME",   "USD"),
    "M2K":  ("M2K",  "CME",   "USD"),
    "YM":   ("YM",   "CBOT",  "USD"),
    "MYM":  ("MYM",  "CBOT",  "USD"),
    "GC":   ("GC",   "NYMEX", "USD"),
    "MGC":  ("MGC",  "NYMEX", "USD"),
    "CL":   ("CL",   "NYMEX", "USD"),
    "MCL":  ("MCL",  "NYMEX", "USD"),
    "SI":   ("SI",   "NYMEX", "USD"),
    "ZN":   ("ZN",   "CBOT",  "USD"),
    "ZB":   ("ZB",   "CBOT",  "USD"),
}


class IBKRBroker(BaseBroker):
    name = "ibkr"
    display_name = "Interactive Brokers"
    supports_futures = True
    supports_forex = True
    supports_stocks = True
    supports_crypto = True

    def __init__(self) -> None:
        self._ib = None
        self._connected = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, **credentials) -> tuple[bool, str]:
        try:
            from ib_insync import IB
        except ImportError:
            return False, (
                "ib_insync is not installed. "
                "Run: pip install ib_insync  then restart the server."
            )

        host = credentials.get("host", "127.0.0.1")
        port = int(credentials.get("port", 7497))
        client_id = int(credentials.get("client_id", 10))

        try:
            ib = IB()
            ib.connect(host, port, clientId=client_id, timeout=15)
            self._ib = ib
            self._connected = True
            accounts = ib.managedAccounts()
            msg = f"Connected. Accounts: {', '.join(accounts)}"
            logger.info("IBKRBroker %s", msg)
            return True, msg
        except Exception as exc:
            self._connected = False
            hint = ""
            if "Connection refused" in str(exc):
                hint = " — Is TWS or IB Gateway running on that host:port?"
            return False, f"IBKR connection failed: {exc}{hint}"

    def disconnect(self) -> None:
        if self._ib:
            try:
                self._ib.disconnect()
            except Exception:
                pass
        self._connected = False

    def is_connected(self) -> bool:
        if not self._ib:
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            return False

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> OrderResult:
        if not self.is_connected():
            return OrderResult(
                order_id="", status="error",
                symbol=symbol, side=side, qty=qty,
                message="Not connected to IBKR",
            )
        try:
            from ib_insync import MarketOrder, LimitOrder
            contract = self._build_contract(symbol)
            order = (
                LimitOrder(side, qty, price)
                if order_type == "LIMIT" and price
                else MarketOrder(side, qty)
            )
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)
            fill_price = trade.orderStatus.avgFillPrice or price
            status = trade.orderStatus.status.lower()
            logger.info("IBKR order: %s %s x%s → %s", side, symbol, qty, status)
            return OrderResult(
                order_id=str(trade.order.orderId),
                status=status,
                symbol=symbol,
                side=side,
                qty=qty,
                fill_price=fill_price,
            )
        except Exception as exc:
            logger.exception("IBKR place_order failed")
            return OrderResult(
                order_id="", status="error",
                symbol=symbol, side=side, qty=qty,
                message=str(exc),
            )

    def close_position(self, symbol: str) -> OrderResult:
        if not self.is_connected():
            return OrderResult(
                order_id="", status="error", symbol=symbol, side="", qty=0
            )
        try:
            clean = self._clean_symbol(symbol)
            for pos in self._ib.positions():
                psym = pos.contract.localSymbol or pos.contract.symbol
                if psym == clean or pos.contract.symbol == clean:
                    qty = abs(int(pos.position))
                    side = "Sell" if pos.position > 0 else "Buy"
                    return self.place_order(symbol, qty, side)
        except Exception:
            logger.exception("IBKR close_position failed")
        return OrderResult(
            order_id="", status="no_position", symbol=symbol, side="", qty=0
        )

    # ── Account ───────────────────────────────────────────────────────────────

    def get_positions(self) -> List[Position]:
        if not self.is_connected():
            return []
        try:
            result = []
            for pos in self._ib.positions():
                result.append(Position(
                    symbol=pos.contract.localSymbol or pos.contract.symbol,
                    qty=int(pos.position),
                    avg_price=float(pos.avgCost or 0),
                    side="Long" if pos.position > 0 else "Short",
                ))
            return result
        except Exception:
            return []

    def get_account_balance(self) -> float:
        if not self.is_connected():
            return 0.0
        try:
            for v in self._ib.accountValues():
                if v.tag == "NetLiquidation" and v.currency == "USD":
                    return float(v.value)
        except Exception:
            pass
        return 0.0

    # ── UI ────────────────────────────────────────────────────────────────────

    def get_connection_fields(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "host",
                "label": "TWS / Gateway Host",
                "type": "text",
                "default": "127.0.0.1",
            },
            {
                "name": "port",
                "label": "Port  (7497 = paper, 7496 = live)",
                "type": "number",
                "default": "7497",
            },
            {
                "name": "client_id",
                "label": "Client ID (any unique number)",
                "type": "number",
                "default": "10",
            },
        ]

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_symbol(tv_symbol: str) -> str:
        sym = tv_symbol.strip().upper()
        if sym.endswith("1!"):
            sym = sym[:-2]
        elif sym.endswith("!"):
            sym = sym[:-1]
        return sym.lstrip("@")

    def _build_contract(self, tv_symbol: str):
        from ib_insync import Stock, Contract

        sym = self._clean_symbol(tv_symbol)
        raw = tv_symbol.strip().upper()

        # Forex: "EUR/USD" or 6-letter alpha "EURUSD"
        if "/" in raw:
            parts = raw.replace("/", "")
            from ib_insync import Forex
            return Forex(parts)

        # Futures: original had "@" prefix or "1!" suffix
        if raw.startswith("@") or raw.endswith("1!") or raw.endswith("!"):
            if sym in _FUTURES_MAP:
                fsym, exch, curr = _FUTURES_MAP[sym]
                c = Contract()
                c.symbol = fsym
                c.secType = "FUT"
                c.exchange = exch
                c.currency = curr
                return c
            # Unknown future — try generic
            c = Contract()
            c.symbol = sym
            c.secType = "FUT"
            c.exchange = "CME"
            c.currency = "USD"
            return c

        # Default: US stock
        return Stock(sym, "SMART", "USD")
