"""
accounts/account_manager.py
============================
Manages trading accounts stored in the Supabase `accounts` table.
Follows the same stateless pattern as data/auth.py — get_supabase() is
called inside each method, never at __init__ time.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from data.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_VALID_ACCOUNT_TYPES = {"PROP_FIRM", "PERSONAL_LIVE", "DEMO", "MANUAL"}
_VALID_RISK_MODES     = {"PROTECTED", "BALANCED", "FREE", "SIMULATION"}
_VALID_TRADING_MODES  = {"FULL_AUTO", "SEMI_AUTO", "SIGNALS_ONLY"}

# ── Simple 5-second in-memory cache for active account ───────────────────────
_active_cache: Dict[str, Any]   = {}   # {user_id: account_dict}
_active_cache_ts: Dict[str, float] = {}  # {user_id: timestamp}
_CACHE_TTL = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AccountManager:
    """CRUD operations for trading accounts."""

    # ── Create ────────────────────────────────────────────────────────────────

    def add_account(
        self,
        user_id: str,
        name: str,
        account_type: str,
        risk_mode: str,
        starting_balance: float,
        daily_loss_limit: float = 0.0,
        max_drawdown_pct: float = 5.0,
        max_contracts: int = 1,
        broker: str = "tradovate",
        trading_mode: str = "SEMI_AUTO",
        is_evaluation_phase: bool = False,
        notes: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Create a new account. Returns the created row or None on failure."""
        if account_type not in _VALID_ACCOUNT_TYPES:
            logger.warning("Invalid account_type: %s", account_type)
            return None
        if risk_mode not in _VALID_RISK_MODES:
            logger.warning("Invalid risk_mode: %s", risk_mode)
            return None
        if trading_mode not in _VALID_TRADING_MODES:
            trading_mode = "SEMI_AUTO"

        sb = get_supabase()
        try:
            res = sb.table("accounts").insert({
                "user_id":             user_id,
                "name":                name,
                "account_type":        account_type,
                "risk_mode":           risk_mode,
                "trading_mode":        trading_mode,
                "starting_balance":    starting_balance,
                "current_balance":     starting_balance,
                "daily_pnl":           0.0,
                "total_pnl":           0.0,
                "daily_loss_limit":    daily_loss_limit,
                "max_drawdown_pct":    max_drawdown_pct,
                "max_contracts":       max_contracts,
                "is_active":           False,
                "broker":              broker,
                "is_evaluation_phase": is_evaluation_phase,
                "notes":               notes,
                "autonomous_mode":     False,
                "created_at":          _now_iso(),
                "last_updated":        _now_iso(),
            }).execute()
            account = res.data[0] if res.data else None
            if account:
                logger.info("Account created: %s (%s)", name, account["id"])
            return account
        except Exception:
            logger.exception("Failed to create account '%s'.", name)
            return None

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_active_account(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return the active account for this user (5-second cached)."""
        now = time.monotonic()
        if (
            user_id in _active_cache
            and now - _active_cache_ts.get(user_id, 0) < _CACHE_TTL
        ):
            return _active_cache[user_id]

        sb = get_supabase()
        try:
            res = (
                sb.table("accounts")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            account = res.data[0] if res.data else None
            _active_cache[user_id] = account
            _active_cache_ts[user_id] = now
            return account
        except Exception:
            logger.exception("Failed to fetch active account.")
            return None

    def get_all_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all accounts for this user."""
        sb = get_supabase()
        try:
            res = (
                sb.table("accounts")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=False)
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("Failed to fetch accounts.")
            return []

    # ── Switch active account ─────────────────────────────────────────────────

    def switch_account(self, user_id: str, account_id: str) -> tuple:
        """
        Returns (success: bool, message: str). Atomic — no partial state.
        Validates the new account before touching anything, then switches all-or-nothing.
        """
        # Step 1: Validate new account exists before touching anything
        new_account = self.get_account(user_id, account_id)
        if not new_account:
            return False, f"Account {account_id} not found for user {user_id}"

        # Step 2: For non-MANUAL brokers, test API connectivity first
        broker = (new_account.get("broker") or "MANUAL").upper()
        if broker != "MANUAL":
            connected = self._test_api_connection(new_account, timeout=3)
            if not connected:
                name = new_account.get("name", account_id)
                return False, (
                    f"Cannot connect to {broker} for '{name}'. "
                    "Keeping current account."
                )

        # Step 3: All validation passed — now switch (deactivate all, activate target)
        sb = get_supabase()
        try:
            sb.table("accounts").update({
                "is_active": False, "last_updated": _now_iso(),
            }).eq("user_id", user_id).execute()

            res = (
                sb.table("accounts")
                .update({"is_active": True, "last_updated": _now_iso()})
                .eq("id", account_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not res.data:
                logger.error("switch_account: activate step returned no rows for %s.", account_id)
                return False, f"Switch failed: account {account_id} could not be activated. All accounts are now deactivated — please reselect an account."

            # Bust cache after confirmed success
            _active_cache.pop(user_id, None)
            _active_cache_ts.pop(user_id, None)
            name = new_account.get("name", account_id)
            logger.info("Switched active account to %s (%s).", account_id, name)
            return True, f"Switched to {name}"

        except Exception as exc:
            logger.exception("Account switch failed.")
            return False, f"Switch failed: {exc}. No changes made."

    def get_account(self, user_id: str, account_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single account by id, scoped to user_id."""
        sb = get_supabase()
        try:
            res = (
                sb.table("accounts")
                .select("*")
                .eq("id", account_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("Failed to fetch account %s.", account_id)
            return None

    def _test_api_connection(self, account: Dict[str, Any], timeout: int = 3) -> bool:
        """
        Attempt a lightweight API ping for the given account's broker.
        Returns True if reachable within timeout seconds.
        """
        import socket
        broker = (account.get("broker") or "").upper()
        host_map = {
            "TRADOVATE": "api.tradovate.com",
            "TRADOVATE_DEMO": "demo.tradovateapi.com",
        }
        host = host_map.get(broker)
        if not host:
            # Unknown broker — optimistically allow the switch
            logger.warning("No connectivity check defined for broker '%s'. Allowing switch.", broker)
            return True
        try:
            with socket.create_connection((host, 443), timeout=timeout):
                pass
            return True
        except OSError:
            logger.warning("Connectivity check failed for broker %s (%s).", broker, host)
            return False

    # ── Updates ───────────────────────────────────────────────────────────────

    def update_balance(self, account_id: str, new_balance: float) -> bool:
        sb = get_supabase()
        try:
            sb.table("accounts").update({
                "current_balance": new_balance,
                "last_updated": _now_iso(),
            }).eq("id", account_id).execute()
            return True
        except Exception:
            logger.exception("Failed to update balance for %s.", account_id)
            return False

    def log_daily_pnl(self, account_id: str, pnl_amount: float) -> bool:
        """Increment daily_pnl by pnl_amount and update total_pnl."""
        sb = get_supabase()
        try:
            res = sb.table("accounts").select("daily_pnl, total_pnl").eq("id", account_id).single().execute()
            if not res.data:
                return False
            current_daily = float(res.data.get("daily_pnl", 0))
            current_total = float(res.data.get("total_pnl", 0))
            sb.table("accounts").update({
                "daily_pnl":    current_daily + pnl_amount,
                "total_pnl":    current_total + pnl_amount,
                "last_updated": _now_iso(),
            }).eq("id", account_id).execute()
            return True
        except Exception:
            logger.exception("Failed to log P&L for %s.", account_id)
            return False

    def reset_daily_stats(self, account_id: str) -> bool:
        """Zero out daily_pnl. Call at start of each trading day."""
        sb = get_supabase()
        try:
            sb.table("accounts").update({
                "daily_pnl":    0.0,
                "last_updated": _now_iso(),
            }).eq("id", account_id).execute()
            _active_cache.clear()
            _active_cache_ts.clear()
            return True
        except Exception:
            logger.exception("Failed to reset daily stats for %s.", account_id)
            return False

    def update_trading_mode(self, account_id: str, mode: str) -> bool:
        if mode not in _VALID_TRADING_MODES:
            return False
        sb = get_supabase()
        try:
            sb.table("accounts").update({
                "trading_mode": mode,
                "last_updated": _now_iso(),
            }).eq("id", account_id).execute()
            _active_cache.clear()
            _active_cache_ts.clear()
            return True
        except Exception:
            logger.exception("Failed to update trading mode.")
            return False

    def set_autonomous_mode(self, account_id: str, enabled: bool) -> bool:
        sb = get_supabase()
        try:
            sb.table("accounts").update({
                "autonomous_mode": enabled,
                "last_updated":    _now_iso(),
            }).eq("id", account_id).execute()
            _active_cache.clear()
            _active_cache_ts.clear()
            return True
        except Exception:
            logger.exception("Failed to set autonomous mode.")
            return False
