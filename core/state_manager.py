"""
core/state_manager.py
======================
Central orchestrator for signal routing and trading mode management.

Signal flow:
  event_bus "tradingview.signal"
      └─> StateManager.on_signal()
              └─> risk check (RiskManager)
              └─> mode routing:
                    FULL_AUTO    → executor immediately
                    SEMI_AUTO    → Telegram approval (60s timeout)
                    SIGNALS_ONLY → Telegram alert, no execution
              └─> high conviction override check (if signal was skipped)
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TRADING_MODES = ["FULL_AUTO", "SEMI_AUTO", "SIGNALS_ONLY"]

# Approval timeout in seconds
_APPROVAL_TIMEOUT = 60.0
_OVERRIDE_TIMEOUT = 90.0

# Pending approvals: signal_id → {"result": None|True|False, "ts": float, "type": "approval"|"override"}
_pending: Dict[str, Dict[str, Any]] = {}


class StateManager:
    """
    Central orchestrator.  Injected dependencies keep circular imports out:
      - telegram_bot injected via set_telegram_bot()
      - trade_executor injected via set_trade_executor()
      - high_conviction_checker injected via set_high_conviction_checker()
    """

    def __init__(self, account_manager, risk_manager) -> None:
        self._account_manager = account_manager
        self._risk_manager    = risk_manager
        self._telegram_bot    = None
        self._executor        = None
        self._hc_checker      = None
        self._user_id: Optional[str] = None   # set when attaching to event bus
        self._session_mode: str = "SEMI_AUTO"  # fallback when no active account

    # ── Dependency injection ──────────────────────────────────────────────────

    def set_telegram_bot(self, bot) -> None:
        self._telegram_bot = bot

    def set_trade_executor(self, executor) -> None:
        self._executor = executor

    def set_high_conviction_checker(self, checker) -> None:
        self._hc_checker = checker

    def set_user_id(self, user_id: str) -> None:
        """Set the user_id to use for Supabase writes (passed from request context)."""
        self._user_id = user_id

    # ── Event bus attachment ──────────────────────────────────────────────────

    def attach_to_event_bus(self, event_bus) -> None:
        event_bus.subscribe("tradingview.signal", self.on_signal)
        logger.info("StateManager subscribed to tradingview.signal events.")

    # ── Signal entry point ────────────────────────────────────────────────────

    def on_signal(self, payload: Dict[str, Any]) -> None:
        """Called by the event bus. Dispatches to a background thread so the webhook returns immediately."""
        threading.Thread(target=self._handle_signal, args=(payload,), daemon=True).start()

    def _handle_signal(self, payload: Dict[str, Any]) -> None:
        uid = self._user_id
        account = None

        if uid:
            account = self._account_manager.get_active_account(uid)
        else:
            account = self._get_any_active_account()
            if account:
                uid = account.get("user_id", "")

        if not uid:
            logger.warning("StateManager: no user_id set and no active account found — signal dropped.")
            return

        result = self.process_signal(payload, account, uid)
        logger.info("Signal processed: action=%s reason=%s", result.get("action"), result.get("reason"))

    def _get_any_active_account(self) -> Optional[Dict[str, Any]]:
        """Fallback for webhook context: return first active account across all users."""
        try:
            from data.supabase_client import get_supabase
            res = get_supabase().table("accounts").select("*").eq("is_active", True).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("Failed to find any active account.")
            return None

    def process_signal(
        self,
        signal: Dict[str, Any],
        account: Optional[Dict[str, Any]],
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Main routing function.
        Returns {"action": "EXECUTE"|"PENDING"|"SKIPPED"|"HALT", "reason": ..., "signal_id": ...}
        """
        signal_id = str(uuid.uuid4())
        signal["_signal_id"] = signal_id

        # ── Risk check ────────────────────────────────────────────────────────
        result = self._risk_manager.check_trade_allowed(account or {}, signal)

        if not result.allowed:
            if result.telegram_message and self._telegram_bot:
                self._telegram_bot.send_risk_alert(result.halt_level, result.telegram_message)
            self.log_autonomous_action(user_id, "RISK_HALT", signal, result.reason, "HALTED")
            return {"action": "HALT", "reason": result.reason, "signal_id": signal_id}

        # Alert on non-zero halt levels (warnings, not blocks)
        if result.halt_level > 0 and result.telegram_message and self._telegram_bot:
            self._telegram_bot.send_risk_alert(result.halt_level, result.telegram_message)

        # Apply risk manager contract cap to signal
        signal["_max_contracts"] = result.max_contracts
        signal["_confidence_threshold"] = result.confidence_threshold

        # Filter by confidence threshold
        confidence = float(signal.get("confidence", 1.0))
        if confidence < result.confidence_threshold:
            logger.info(
                "Signal below confidence threshold (%.2f < %.2f) — skipped.",
                confidence, result.confidence_threshold,
            )
            return {
                "action": "SKIPPED",
                "reason": f"Confidence {confidence:.2f} < threshold {result.confidence_threshold:.2f}",
                "signal_id": signal_id,
            }

        # Filter by allowed strategies (L3 PROTECTED mode)
        if result.allowed_strategies:
            strategy = (signal.get("strategy") or "").upper()
            if not any(k in strategy for k in result.allowed_strategies):
                return {
                    "action": "SKIPPED",
                    "reason": f"Strategy '{strategy}' not in allowed list {result.allowed_strategies}",
                    "signal_id": signal_id,
                }

        # ── Mode routing ──────────────────────────────────────────────────────
        mode = self.get_current_mode(account)

        if mode == "FULL_AUTO":
            return self._route_full_auto(signal, user_id, signal_id)

        if mode == "SEMI_AUTO":
            return self._route_semi_auto(signal, user_id, signal_id)

        if mode == "SIGNALS_ONLY":
            return self._route_signals_only(signal, user_id, signal_id)

        return {"action": "SKIPPED", "reason": f"Unknown mode: {mode}", "signal_id": signal_id}

    # ── Mode routing helpers ──────────────────────────────────────────────────

    def _route_full_auto(
        self, signal: Dict[str, Any], user_id: str, signal_id: str
    ) -> Dict[str, Any]:
        self._execute(signal, user_id)
        if self._telegram_bot:
            self._telegram_bot.send_trade_executed(signal, {"mode": "FULL_AUTO"})
        self.log_autonomous_action(user_id, "AUTONOMOUS_ENTRY", signal, "FULL_AUTO mode", "PENDING")
        return {"action": "EXECUTE", "reason": "FULL_AUTO", "signal_id": signal_id}

    def _route_semi_auto(
        self, signal: Dict[str, Any], user_id: str, signal_id: str
    ) -> Dict[str, Any]:
        if self._telegram_bot:
            self._telegram_bot.send_signal_alert(signal, "SEMI_AUTO")

        # Store pending approval
        _pending[signal_id] = {"result": None, "ts": time.monotonic(), "type": "approval"}

        # Poll for response (2-second intervals, 60-second total)
        deadline = time.monotonic() + _APPROVAL_TIMEOUT
        while time.monotonic() < deadline:
            entry = _pending.get(signal_id, {})
            if entry.get("result") is True:
                _pending.pop(signal_id, None)
                self._execute(signal, user_id)
                return {"action": "EXECUTE", "reason": "SEMI_AUTO approved", "signal_id": signal_id}
            if entry.get("result") is False:
                _pending.pop(signal_id, None)
                return {"action": "SKIPPED", "reason": "SEMI_AUTO rejected", "signal_id": signal_id}
            time.sleep(2)

        # Timeout — check for high conviction override
        _pending.pop(signal_id, None)
        logger.info("SEMI_AUTO approval timed out for signal %s.", signal_id)
        self._maybe_override(signal, user_id, signal_id, "SEMI_AUTO approval timeout")
        return {"action": "SKIPPED", "reason": "SEMI_AUTO timeout", "signal_id": signal_id}

    def _route_signals_only(
        self, signal: Dict[str, Any], user_id: str, signal_id: str
    ) -> Dict[str, Any]:
        if self._telegram_bot:
            self._telegram_bot.send_signal_alert(signal, "SIGNALS_ONLY")
        # Store "did you take this?" pending
        _pending[signal_id] = {"result": None, "ts": time.monotonic(), "type": "manual_track"}
        return {"action": "PENDING", "reason": "SIGNALS_ONLY — alert sent", "signal_id": signal_id}

    # ── High conviction override ───────────────────────────────────────────────

    def _maybe_override(
        self,
        signal: Dict[str, Any],
        user_id: str,
        signal_id: str,
        blocked_reason: str,
    ) -> None:
        if not self._hc_checker or not self._telegram_bot:
            return
        account = self._account_manager.get_active_account(user_id)
        override = self._hc_checker.check_high_conviction_override(signal, {}, account or {})
        if not override:
            return

        override["why_blocked"] = blocked_reason
        override_id = f"override_{signal_id}"
        _pending[override_id] = {"result": None, "ts": time.monotonic(), "type": "override"}

        self._telegram_bot.send_override_request(signal, override)

        # Wait up to 90 seconds for response
        deadline = time.monotonic() + _OVERRIDE_TIMEOUT
        while time.monotonic() < deadline:
            entry = _pending.get(override_id, {})
            if entry.get("result") is True:
                _pending.pop(override_id, None)
                # PROTECTED accounts: notify only, never auto-enter
                risk_mode = (account or {}).get("risk_mode", "BALANCED").upper()
                if risk_mode == "PROTECTED":
                    logger.info("Override approved but PROTECTED account — not executing.")
                    return
                signal["_max_contracts"] = override.get("recommended_contracts", 1)
                self._execute(signal, user_id)
                self.log_autonomous_action(user_id, "OVERRIDE_APPROVED", signal, override.get("why_still_good", ""), "PENDING")
                return
            if entry.get("result") is False:
                _pending.pop(override_id, None)
                self.log_autonomous_action(user_id, "OVERRIDE_SKIPPED", signal, blocked_reason, "SKIPPED")
                return
            time.sleep(2)

        # Timeout — auto-enter with 1 contract for non-PROTECTED accounts
        _pending.pop(override_id, None)
        risk_mode = (account or {}).get("risk_mode", "BALANCED").upper()
        if risk_mode != "PROTECTED":
            signal["_max_contracts"] = 1
            self._execute(signal, user_id)
            self.log_autonomous_action(user_id, "OVERRIDE_TIMEOUT", signal, "90s no response — entered 1 contract", "PENDING")

    # ── Execution passthrough ─────────────────────────────────────────────────

    def _execute(self, signal: Dict[str, Any], user_id: str) -> None:
        if self._executor:
            self._executor.on_signal(signal)

    # ── Approval callbacks (called by Telegram bot) ───────────────────────────

    def set_approval_result(self, signal_id: str, approved: bool) -> bool:
        """Called by TelegramBot when user taps Approve/Reject."""
        if signal_id in _pending:
            _pending[signal_id]["result"] = approved
            return True
        # Also check override IDs
        override_id = f"override_{signal_id}"
        if override_id in _pending:
            _pending[override_id]["result"] = approved
            return True
        return False

    def get_pending_signal(self) -> Optional[Dict[str, Any]]:
        """Return metadata of the oldest pending approval (for dashboard polling)."""
        now = time.monotonic()
        for sid, entry in list(_pending.items()):
            if entry["type"] == "approval" and entry["result"] is None:
                age = now - entry["ts"]
                if age < _APPROVAL_TIMEOUT:
                    return {"signal_id": sid, "seconds_remaining": int(_APPROVAL_TIMEOUT - age)}
        return None

    def set_manual_track_result(self, signal_id: str, took_trade: bool, entry_price: Optional[float] = None) -> None:
        """Called from Telegram when user answers 'Did you take this trade?'."""
        entry = _pending.pop(signal_id, None)
        if entry:
            logger.info(
                "Manual track: signal_id=%s took=%s entry=%s",
                signal_id, took_trade, entry_price,
            )

    # ── Trading mode ──────────────────────────────────────────────────────────

    def get_current_mode(self, account: Optional[Dict[str, Any]]) -> str:
        if account:
            return (account.get("trading_mode") or "SEMI_AUTO").upper()
        return self._session_mode

    def set_trading_mode(self, mode: str, account_id: str, user_id: str) -> bool:
        if mode not in TRADING_MODES:
            return False
        ok = self._account_manager.update_trading_mode(account_id, mode)
        if ok:
            logger.info("Trading mode set to %s on account %s.", mode, account_id)
            if self._telegram_bot:
                account = self._account_manager.get_active_account(user_id)
                name = (account or {}).get("name", account_id)
                self._telegram_bot.send_message(f"⚙️ Trading mode changed to {mode} on {name}.")
        return ok

    # ── Autonomous mode ───────────────────────────────────────────────────────

    def toggle_autonomous_mode(
        self,
        enable: bool,
        account_id: str,
        user_id: str,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Enable/disable autonomous mode.
        Returns {"status": "ok"|"confirm_required"|"error", "message": str}
        """
        account = self._account_manager.get_active_account(user_id)
        if not account:
            return {"status": "error", "message": "No active account."}

        risk_mode = (account.get("risk_mode") or "BALANCED").upper()
        if enable and risk_mode == "PROTECTED":
            return {
                "status": "error",
                "message": "Autonomous mode is not available for PROTECTED accounts.",
            }

        if enable and not confirmed:
            return {
                "status": "confirm_required",
                "message": (
                    f"⚠️ You are enabling AUTONOMOUS MODE on {account['name']}.\n"
                    "The bot will enter trades WITHOUT your approval.\n"
                    "Hard risk limits still apply.\n"
                    "Reply with CONFIRM to proceed."
                ),
            }

        ok = self._account_manager.set_autonomous_mode(account_id, enable)
        if ok and self._telegram_bot:
            state = "ENABLED" if enable else "DISABLED"
            self._telegram_bot.send_message(
                f"{'🟢' if enable else '🔴'} Autonomous mode {state} on {account['name']}."
            )
        return {"status": "ok" if ok else "error", "message": "Autonomous mode updated." if ok else "Update failed."}

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_autonomous_action(
        self,
        user_id: str,
        action_type: str,
        signal: Dict[str, Any],
        reasoning: str,
        outcome: str,
    ) -> None:
        """Insert a row into the autonomous_log Supabase table."""
        try:
            from data.supabase_client import get_supabase
            import json
            # Strip internal keys before storing
            clean = {k: v for k, v in signal.items() if not k.startswith("_")}
            get_supabase().table("autonomous_log").insert({
                "user_id":     user_id,
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "type":        action_type,
                "strategy":    signal.get("strategy", ""),
                "signal_json": clean,
                "reasoning":   reasoning,
                "outcome":     outcome,
            }).execute()
        except Exception:
            logger.exception("Failed to write autonomous_log entry.")
