"""
broker/paper_broker.py
======================
Built-in paper trading — no external account needed.
Simulates fills instantly at the signal price.
Persists every trade to the Supabase `trades` table.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from broker.base_broker import BaseBroker, OrderResult, Position

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperBroker(BaseBroker):
    name = "paper"
    display_name = "Built-in Paper Trading"
    supports_futures = True
    supports_forex = True
    supports_stocks = True
    supports_crypto = True

    def __init__(self) -> None:
        self._balance: float = 100_000.0
        self._starting_balance: float = 100_000.0
        self._positions: Dict[str, Position] = {}
        self._lock = Lock()
        self._connected: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, **credentials) -> tuple[bool, str]:
        balance = float(credentials.get("starting_balance", 100_000.0))
        with self._lock:
            self._balance = balance
            self._starting_balance = balance
            self._positions = {}
            self._connected = True
        logger.info("PaperBroker connected — starting balance $%,.0f", balance)
        return True, f"Paper trading ready. Balance: ${balance:,.0f}"

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> OrderResult:
        fill_price = price or 0.0
        with self._lock:
            if side == "Buy":
                cost = fill_price * qty if fill_price else 0
                self._balance -= cost
                if symbol in self._positions:
                    pos = self._positions[symbol]
                    total = pos.qty + qty
                    if fill_price and total:
                        pos.avg_price = (pos.avg_price * pos.qty + fill_price * qty) / total
                    pos.qty = total
                else:
                    self._positions[symbol] = Position(
                        symbol=symbol, qty=qty, avg_price=fill_price, side="Long"
                    )
            elif side == "Sell":
                proceeds = fill_price * qty if fill_price else 0
                self._balance += proceeds
                if symbol in self._positions:
                    pos = self._positions[symbol]
                    pos.qty -= qty
                    if pos.qty <= 0:
                        del self._positions[symbol]

        order_id = str(uuid.uuid4())[:8]
        self._log_trade(symbol, side, qty, fill_price, order_id)
        logger.info("[PAPER] %s %s x%s @ %.4f | balance=$%,.0f",
                    side, symbol, qty, fill_price, self._balance)
        return OrderResult(
            order_id=order_id, status="filled",
            symbol=symbol, side=side, qty=qty, fill_price=fill_price,
        )

    def close_position(self, symbol: str) -> OrderResult:
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                logger.info("[PAPER] No position to close for %s.", symbol)
                return OrderResult(
                    order_id="", status="no_position",
                    symbol=symbol, side="", qty=0,
                )
            qty = pos.qty
            avg_price = pos.avg_price
            del self._positions[symbol]
            side = "Sell" if qty > 0 else "Buy"

        order_id = str(uuid.uuid4())[:8]
        self._log_trade(symbol, side, abs(qty), avg_price, order_id, action="CLOSE")
        logger.info("[PAPER] Closed %s x%s @ %.4f", symbol, abs(qty), avg_price)
        return OrderResult(
            order_id=order_id, status="filled",
            symbol=symbol, side=side, qty=abs(qty), fill_price=avg_price,
        )

    # ── Account ───────────────────────────────────────────────────────────────

    def get_positions(self) -> List[Position]:
        with self._lock:
            return list(self._positions.values())

    def get_account_balance(self) -> float:
        return self._balance

    def get_pnl(self) -> float:
        return round(self._balance - self._starting_balance, 2)

    # ── UI ────────────────────────────────────────────────────────────────────

    def get_connection_fields(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "starting_balance",
                "label": "Starting Balance ($)",
                "type": "number",
                "default": "100000",
            }
        ]

    def status_dict(self) -> Dict[str, Any]:
        d = super().status_dict()
        d.update({
            "balance": self._balance,
            "pnl": self.get_pnl(),
            "open_positions": len(self._positions),
        })
        return d

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log_trade(
        self, symbol: str, side: str, qty: int,
        price: float, order_id: str, action: str = "ORDER",
    ) -> None:
        try:
            from data.supabase_client import get_supabase
            sb = get_supabase()
            sb.table("trades").insert({
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "fill_price": price,
                "broker": "paper",
                "status": "filled",
                "order_id": order_id,
                "action": action,
                "created_at": _now_iso(),
            }).execute()
        except Exception:
            pass
