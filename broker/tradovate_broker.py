"""
broker/tradovate_broker.py
==========================
Tradovate adapter — wraps the existing TradovateClient into the BaseBroker interface.
Futures only (MES, MNQ, ES, NQ, and all Tradovate-listed contracts).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from broker.base_broker import BaseBroker, OrderResult, Position
from broker.tradovate_client import TradovateClient

logger = logging.getLogger(__name__)

_TV_TO_TRADOVATE = {"Buy": "Buy", "Sell": "Sell"}


def _normalize(tv_symbol: str) -> str:
    sym = tv_symbol.strip()
    if sym.endswith("1!"):
        sym = sym[:-2]
    elif sym.endswith("!"):
        sym = sym[:-1]
    if not sym.startswith("@"):
        sym = f"@{sym}"
    return sym


class TradovateBroker(BaseBroker):
    name = "tradovate"
    display_name = "Tradovate"
    supports_futures = True
    supports_forex = False
    supports_stocks = False
    supports_crypto = False

    def __init__(self) -> None:
        self._client: Optional[TradovateClient] = None
        self._account_id: Optional[int] = None
        self._account_spec: Optional[str] = None
        self._connected = False
        self._order_qty = int(os.getenv("ORDER_QTY", "1"))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, **credentials) -> tuple[bool, str]:
        base_url   = credentials.get("base_url",    os.getenv("TRADOVATE_API_BASE_URL", "https://demo-api.tradovate.com"))
        username   = credentials.get("username",    os.getenv("TRADOVATE_USERNAME", ""))
        password   = credentials.get("password",    os.getenv("TRADOVATE_PASSWORD", ""))
        client_id  = credentials.get("client_id",   os.getenv("TRADOVATE_CLIENT_ID", ""))
        client_sec = credentials.get("client_secret", os.getenv("TRADOVATE_CLIENT_SECRET", ""))

        if not all([username, password, client_id, client_sec]):
            return False, "Missing Tradovate credentials. Fill them in the connect form."

        self._client = TradovateClient(
            base_url=base_url,
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_sec,
        )
        try:
            accounts = self._client.get_accounts()
            if not accounts:
                return False, "No Tradovate accounts found. Check credentials."
            acct = accounts[0]
            self._account_id   = int(acct["id"])
            self._account_spec = str(acct.get("name", self._account_id))
            self._connected    = True
            msg = f"Connected to Tradovate. Account: {self._account_spec}"
            logger.info(msg)
            return True, msg
        except Exception as exc:
            self._connected = False
            return False, f"Tradovate connection failed: {exc}"

    def disconnect(self) -> None:
        self._connected = False
        self._client    = None

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> OrderResult:
        if not self.is_connected() or self._account_id is None:
            return OrderResult(
                order_id="", status="error",
                symbol=symbol, side=side, qty=qty,
                message="Not connected to Tradovate",
            )
        tradovate_sym = _normalize(symbol)
        try:
            result = self._client.place_order(
                account_id=self._account_id,
                account_spec=self._account_spec,
                symbol=tradovate_sym,
                action=side,
                qty=qty,
            )
            order_id = str(result.get("orderId", result.get("id", "")))
            logger.info("Tradovate order: %s %s x%s → %s", side, tradovate_sym, qty, result)
            return OrderResult(
                order_id=order_id, status="filled",
                symbol=symbol, side=side, qty=qty,
            )
        except Exception as exc:
            logger.exception("Tradovate place_order failed")
            return OrderResult(
                order_id="", status="error",
                symbol=symbol, side=side, qty=qty, message=str(exc),
            )

    def close_position(self, symbol: str) -> OrderResult:
        if not self.is_connected():
            return OrderResult(
                order_id="", status="error", symbol=symbol, side="", qty=0
            )
        try:
            positions = self._client.get_positions()
            if not positions:
                return OrderResult(
                    order_id="", status="no_position", symbol=symbol, side="", qty=0
                )
            for pos in positions:
                pos_id = pos.get("id")
                if pos_id is not None:
                    self._client.liquidate_position(int(pos_id))
                    logger.info("Tradovate liquidated position id=%s", pos_id)
            return OrderResult(
                order_id="close", status="filled", symbol=symbol, side="Sell", qty=0
            )
        except Exception as exc:
            logger.exception("Tradovate close_position failed")
            return OrderResult(
                order_id="", status="error", symbol=symbol, side="", qty=0, message=str(exc)
            )

    # ── Account ───────────────────────────────────────────────────────────────

    def get_positions(self) -> List[Position]:
        if not self.is_connected():
            return []
        try:
            raw = self._client.get_positions()
            result = []
            for p in raw:
                result.append(Position(
                    symbol=str(p.get("contractId", p.get("symbol", ""))),
                    qty=int(p.get("netPos", 0)),
                    avg_price=float(p.get("avgPrice", 0)),
                ))
            return result
        except Exception:
            return []

    def get_account_balance(self) -> float:
        if not self.is_connected():
            return 0.0
        try:
            accounts = self._client.get_accounts()
            if accounts:
                return float(accounts[0].get("balance", 0))
        except Exception:
            pass
        return 0.0

    # ── UI ────────────────────────────────────────────────────────────────────

    def get_connection_fields(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "base_url",
                "label": "API URL (demo or live)",
                "type": "text",
                "default": "https://demo-api.tradovate.com",
            },
            {"name": "username",      "label": "Tradovate Username",  "type": "text",     "default": ""},
            {"name": "password",      "label": "Tradovate Password",  "type": "password", "default": ""},
            {"name": "client_id",     "label": "App Client ID",       "type": "text",     "default": ""},
            {"name": "client_secret", "label": "App Client Secret",   "type": "password", "default": ""},
        ]
