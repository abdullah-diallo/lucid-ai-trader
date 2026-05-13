"""
risk/risk_manager.py
====================
Pure, stateless risk calculator.  Reads account state and returns a
RiskCheckResult — it never modifies Supabase or calls Telegram directly.
The caller (StateManager) is responsible for acting on the result.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, time as _time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Strategies considered "highest quality" for prop-firm protection level 3
_L3_ALLOWED_STRATEGIES = {"ORB", "SMC", "BOS"}

# Confidence level → contract count scaling for FREE mode
_FREE_CONTRACT_SCALE = [
    (0.85, 3),
    (0.75, 2),
    (0.65, 1),
]

_EASTERN = ZoneInfo("America/New_York")

# Per-session and daily trade caps (ICT session names)
SESSION_TRADE_LIMITS: Dict[str, int] = {
    "LONDON": 2,
    "NY_OPEN": 3,
    "NY_PM": 1,
    "TOTAL_DAY": 6,
}


@dataclass
class RiskCheckResult:
    allowed: bool
    halt_level: int = 0            # 0=ok, 1-5 (5 = hard halt)
    reason: str = ""
    confidence_threshold: float = 0.65
    allowed_strategies: Optional[List[str]] = None  # None = all strategies OK
    max_contracts: int = 1
    telegram_message: str = ""
    stop_tighten: bool = False     # True at L2 — caller should reduce stop size


class RiskManager:
    """
    Account-aware risk calculator.

    Usage:
        result = risk_manager.check_trade_allowed(account, signal)
        if not result.allowed:
            # log halt, notify, skip trade
    """

    # ── Initialisation ────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._risk_lock = threading.Lock()
        self.session_trades: Dict[str, int] = {"LONDON": 0, "NY_OPEN": 0, "NY_PM": 0}
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.is_trading_halted: bool = False
        self.halt_reason: str = ""
        self.current_balance: float = 0.0
        self.peak_balance: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def can_take_trade(
        self,
        account: Dict[str, Any],
        signal: Dict[str, Any],
        open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> RiskCheckResult:
        """Thread-safe trade gate. All checks run inside a single mutex."""
        with self._risk_lock:
            if not account:
                return RiskCheckResult(
                    allowed=False,
                    reason="No active account",
                    telegram_message="⚠️ No active account configured.",
                )

            # Sync realized P&L from the account record into instance state
            self.daily_pnl = float(account.get("daily_pnl", self.daily_pnl))

            if self.is_trading_halted:
                return RiskCheckResult(
                    allowed=False,
                    reason=self.halt_reason or "Trading halted",
                    telegram_message=f"🛑 Trading is halted. {self.halt_reason}",
                )

            if self.daily_trades >= SESSION_TRADE_LIMITS["TOTAL_DAY"]:
                return RiskCheckResult(
                    allowed=False,
                    reason=(
                        f"Daily trade cap reached: "
                        f"{self.daily_trades}/{SESSION_TRADE_LIMITS['TOTAL_DAY']}"
                    ),
                )

            current_session = self._get_ict_session(datetime.now(_EASTERN))
            session_count = self.session_trades.get(current_session, 0)
            session_limit = SESSION_TRADE_LIMITS.get(current_session, 99)
            if session_count >= session_limit:
                return RiskCheckResult(
                    allowed=False,
                    reason=(
                        f"Session limit reached: "
                        f"{session_count}/{session_limit} for {current_session}"
                    ),
                )

            risk_mode = (account.get("risk_mode") or "BALANCED").upper()
            handlers = {
                "PROTECTED":  self._check_protected,
                "BALANCED":   self._check_balanced,
                "FREE":       self._check_free,
                "SIMULATION": self._check_simulation,
            }
            handler = handlers.get(risk_mode, self._check_balanced)
            if risk_mode == "PROTECTED":
                return handler(account, signal, open_positions or [])
            return handler(account, signal)

    def check_trade_allowed(
        self,
        account: Dict[str, Any],
        signal: Dict[str, Any],
        open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> RiskCheckResult:
        """Backward-compatible alias for can_take_trade()."""
        return self.can_take_trade(account, signal, open_positions)

    def increment_session_trade(self) -> None:
        """Call this after a trade is successfully placed."""
        session = self._get_ict_session(datetime.now(_EASTERN))
        self.session_trades[session] = self.session_trades.get(session, 0) + 1
        self.daily_trades += 1

    def get_risk_status(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """Return dashboard-facing risk summary for the active account."""
        if not account:
            return {"error": "No active account"}

        risk_mode   = (account.get("risk_mode") or "BALANCED").upper()
        daily_pnl   = float(account.get("daily_pnl", 0))
        dll         = float(account.get("daily_loss_limit", 0))
        start_bal   = float(account.get("starting_balance", 1))
        current_bal = float(account.get("current_balance", start_bal))

        dll_used_pct    = abs(daily_pnl) / dll if dll > 0 else 0.0
        drawdown_pct    = (start_bal - current_bal) / start_bal * 100 if start_bal > 0 else 0.0
        max_dd_pct      = float(account.get("max_drawdown_pct", 5.0))

        halt_level = 0
        if risk_mode == "PROTECTED" and dll > 0:
            if dll_used_pct >= 0.80:
                halt_level = 4
            elif dll_used_pct >= 0.70:
                halt_level = 3
            elif dll_used_pct >= 0.50:
                halt_level = 2
            elif dll_used_pct >= 0.25:
                halt_level = 1
        if risk_mode == "PROTECTED" and drawdown_pct >= max_dd_pct:
            halt_level = 5

        return {
            "risk_mode":         risk_mode,
            "trading_mode":      account.get("trading_mode", "SEMI_AUTO"),
            "autonomous_mode":   account.get("autonomous_mode", False),
            "daily_pnl":         daily_pnl,
            "daily_loss_limit":  dll,
            "dll_used_pct":      round(dll_used_pct * 100, 1),
            "drawdown_pct":      round(drawdown_pct, 2),
            "max_drawdown_pct":  max_dd_pct,
            "halt_level":        halt_level,
            "is_halted":         halt_level >= 4,
            "current_balance":   current_bal,
            "starting_balance":  start_bal,
        }

    def can_override_halt(self, account: Dict[str, Any]) -> bool:
        """True only for L4 (soft halt). L5 (hard halt) cannot be overridden."""
        status = self.get_risk_status(account)
        return status.get("halt_level") == 4

    # ── Exposure & position helpers ───────────────────────────────────────────

    def get_total_exposure(self, open_positions: List[Dict[str, Any]]) -> float:
        """Returns realized daily P&L + unrealized P&L across all open positions."""
        POINT_VALUE: Dict[str, float] = {"MES": 5.0, "MNQ": 2.0}
        unrealized = 0.0
        for pos in open_positions:
            instrument = pos.get("instrument", "MES")
            multiplier = POINT_VALUE.get(instrument, 5.0)
            pnl = (pos["current_price"] - pos["entry_price"]) * multiplier * pos["contracts"]
            if pos["direction"] == "SHORT":
                pnl = -pnl
            unrealized += pnl
        return self.daily_pnl + unrealized

    async def check_positions_before_news(
        self,
        open_positions: List[Dict[str, Any]],
        minutes_to_news: int,
        account_mode: str,
    ) -> Optional[str]:
        """
        If high-impact news is within 5 minutes, returns an alert message.
        Caller is responsible for sending the Telegram notification and handling
        auto-close logic (60s window for PROTECTED, alert-only for FREE).
        """
        if minutes_to_news > 5 or not open_positions:
            return None

        profitable = [p for p in open_positions if p.get("unrealized_pnl", 0) > 0]
        if not profitable:
            return None

        if account_mode == "PROTECTED":
            return (
                f"⚠️ HIGH IMPACT NEWS IN {minutes_to_news} MIN\n"
                f"You have {len(profitable)} profitable position(s).\n"
                f"Close to protect gains? [Yes — Close All] [No — Hold]\n"
                f"Auto-closing in 60 seconds if no response."
            )
        # FREE / BALANCED — alert only, never auto-close
        return (
            f"⚠️ News in {minutes_to_news} min. "
            f"You have {len(open_positions)} open position(s). Consider closing."
        )

    def reset_daily(self, account: Dict[str, Any]) -> None:
        """
        Call at 5 PM ET. Resets all daily counters and halts prop accounts
        until the user sends /resume the next morning.
        """
        # Carry realized P&L into running balance
        self.current_balance = (
            float(account.get("current_balance", self.current_balance)) + self.daily_pnl
        )
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        # Reset daily counters
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.session_trades = {"LONDON": 0, "NY_OPEN": 0, "NY_PM": 0}

        risk_mode = (account.get("risk_mode") or "BALANCED").upper()
        if risk_mode == "PROTECTED":
            self.is_trading_halted = True
            self.halt_reason = "End of day. Send /resume to start trading tomorrow."
        else:
            self.is_trading_halted = False
            self.halt_reason = ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_ict_session(self, now: datetime) -> str:
        """Map a datetime to an ICT session key for session trade limit checks."""
        t = now.astimezone(_EASTERN).time()
        if _time(2, 0) <= t < _time(5, 0):
            return "LONDON"
        if _time(7, 0) <= t < _time(12, 0):
            return "NY_OPEN"
        if _time(14, 0) <= t < _time(16, 0):
            return "NY_PM"
        return "OTHER"

    # ── Mode handlers (private) ───────────────────────────────────────────────

    def _check_protected(
        self,
        account: Dict[str, Any],
        signal: Dict[str, Any],
        open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> RiskCheckResult:
        """5-level safety ladder for prop firm accounts."""
        # Use total exposure (realized + unrealized) when positions are supplied
        daily_pnl  = (
            self.get_total_exposure(open_positions)
            if open_positions is not None
            else float(account.get("daily_pnl", 0))
        )
        dll        = float(account.get("daily_loss_limit", 0))
        start_bal  = float(account.get("starting_balance", 1))
        curr_bal   = float(account.get("current_balance", start_bal))
        max_dd_pct = float(account.get("max_drawdown_pct", 5.0))
        acct_name  = account.get("name", "Account")

        # Level 5: max drawdown reached
        drawdown_pct = (start_bal - curr_bal) / start_bal * 100 if start_bal > 0 else 0
        if drawdown_pct >= max_dd_pct:
            return RiskCheckResult(
                allowed=False,
                halt_level=5,
                reason=f"Max drawdown {drawdown_pct:.1f}% ≥ limit {max_dd_pct}%",
                telegram_message=(
                    f"🚨 MAX DRAWDOWN LIMIT REACHED on {acct_name}.\n"
                    f"Drawdown: {drawdown_pct:.1f}% / {max_dd_pct}%\n"
                    f"Account protected. Type /resume to re-enable after reviewing."
                ),
            )

        if dll <= 0:
            # No DLL configured — treat as BALANCED
            return self._check_balanced(account, signal)

        dll_used_pct = abs(daily_pnl) / dll

        # Level 4: 80%+ DLL — hard stop
        if dll_used_pct >= 0.80:
            buffer = dll - abs(daily_pnl)
            return RiskCheckResult(
                allowed=False,
                halt_level=4,
                reason=f"DLL 80%+ used ({dll_used_pct*100:.0f}%)",
                telegram_message=(
                    f"🛑 Trading halted on {acct_name}.\n"
                    f"${abs(daily_pnl):.0f} of ${dll:.0f} DLL used.\n"
                    f"${buffer:.0f} buffer preserved. Type /resume when ready."
                ),
            )

        # Level 3: 70%+ DLL — high-quality strategies only, 1 contract
        if dll_used_pct >= 0.70:
            strategy = (signal.get("strategy") or "").upper()
            strategy_key = next((k for k in _L3_ALLOWED_STRATEGIES if k in strategy), None)
            if not strategy_key:
                return RiskCheckResult(
                    allowed=False,
                    halt_level=3,
                    reason=f"L3 caution: only ORB/SMC/BOS allowed, got {strategy}",
                    max_contracts=1,
                    telegram_message=(
                        f"🔴 L3 caution on {acct_name} — "
                        f"{dll_used_pct*100:.0f}% DLL used. "
                        f"Signal {strategy} blocked (only ORB/SMC/BOS allowed)."
                    ),
                )
            return RiskCheckResult(
                allowed=True,
                halt_level=3,
                reason="L3: high-quality strategy allowed",
                max_contracts=1,
                telegram_message=(
                    f"🔴 {acct_name} at L3 ({dll_used_pct*100:.0f}% DLL). "
                    f"Allowing {strategy} with max 1 contract."
                ),
            )

        # Level 2: 50%+ DLL — tighten thresholds
        if dll_used_pct >= 0.50:
            return RiskCheckResult(
                allowed=True,
                halt_level=2,
                reason="L2: tightened risk",
                confidence_threshold=0.72,
                stop_tighten=True,
                max_contracts=account.get("max_contracts", 1),
                telegram_message=(
                    f"⚠️ {acct_name} at 50% DLL "
                    f"(${abs(daily_pnl):.0f}/${dll:.0f}) — "
                    f"tightening: threshold 0.72, stops reduced 20%."
                ),
            )

        # Level 1: 25%+ DLL — alert only
        if dll_used_pct >= 0.25:
            return RiskCheckResult(
                allowed=True,
                halt_level=1,
                reason="L1: DLL 25% used, monitoring",
                max_contracts=account.get("max_contracts", 1),
                telegram_message=(
                    f"⚠️ 25% of daily limit used on {acct_name} — "
                    f"${abs(daily_pnl):.0f} of ${dll:.0f}."
                ),
            )

        # Level 0: all clear
        return RiskCheckResult(
            allowed=True,
            halt_level=0,
            reason="PROTECTED: all limits clear",
            max_contracts=account.get("max_contracts", 1),
        )

    def _check_balanced(
        self, account: Dict[str, Any], signal: Dict[str, Any]
    ) -> RiskCheckResult:
        """Soft limits — advisory only, no hard stops."""
        daily_pnl = float(account.get("daily_pnl", 0))
        dll       = float(account.get("daily_loss_limit", 0))
        acct_name = account.get("name", "Account")

        message = ""
        if dll > 0 and abs(daily_pnl) >= dll * 0.80:
            message = (
                f"⚠️ {acct_name} is near daily limit "
                f"(${abs(daily_pnl):.0f} / ${dll:.0f}). Advisory only."
            )

        return RiskCheckResult(
            allowed=True,
            halt_level=0,
            reason="BALANCED: soft limits",
            max_contracts=account.get("max_contracts", 1),
            telegram_message=message,
        )

    def _check_free(
        self, account: Dict[str, Any], signal: Dict[str, Any]
    ) -> RiskCheckResult:
        """No hard limits. Contract count scales with signal confidence."""
        confidence = float(signal.get("confidence", 0.65))
        max_acct   = int(account.get("max_contracts", 3))

        contracts = 1
        for threshold, qty in _FREE_CONTRACT_SCALE:
            if confidence >= threshold:
                contracts = min(qty, max_acct)
                break

        return RiskCheckResult(
            allowed=True,
            halt_level=0,
            reason=f"FREE: {contracts} contract(s) at {confidence:.0%} confidence",
            max_contracts=contracts,
        )

    def _check_simulation(
        self, account: Dict[str, Any], signal: Dict[str, Any]
    ) -> RiskCheckResult:
        """Demo/paper mode — lower confidence threshold, permissive."""
        return RiskCheckResult(
            allowed=True,
            halt_level=0,
            reason="SIMULATION: paper mode",
            confidence_threshold=0.55,
            max_contracts=account.get("max_contracts", 1),
        )
