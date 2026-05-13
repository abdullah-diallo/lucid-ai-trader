"""
tests/test_risk_manager.py
==========================
Chapter 3 verification — 5 tests for risk management hardening.
Run: python -m pytest tests/test_risk_manager.py -v --tb=short
"""
import threading
import time
import unittest
from unittest.mock import patch

from risk.risk_manager import RiskManager, SESSION_TRADE_LIMITS


def _account(risk_mode="PROTECTED", daily_pnl=0.0, dll=1000.0,
             start=50_000.0, current=50_000.0):
    return {
        "name": "TestAccount",
        "risk_mode": risk_mode,
        "daily_pnl": daily_pnl,
        "daily_loss_limit": dll,
        "starting_balance": start,
        "current_balance": current,
        "max_drawdown_pct": 5.0,
        "max_contracts": 1,
    }


def _signal(strategy="ORB", confidence=0.80):
    return {"strategy": strategy, "confidence": confidence}


class TestAtomicLock(unittest.TestCase):

    def test_atomic_lock_prevents_simultaneous_approval(self):
        """Lock must ensure at most one thread is executing can_take_trade() at a time."""
        rm = RiskManager()
        inside = [0]
        peak_concurrent = [0]
        original_check = rm._check_balanced

        def slow_check(account, signal):
            inside[0] += 1
            peak_concurrent[0] = max(peak_concurrent[0], inside[0])
            time.sleep(0.05)
            result = original_check(account, signal)
            inside[0] -= 1
            return result

        rm._check_balanced = slow_check
        acct = _account(risk_mode="BALANCED")
        results = []
        barrier = threading.Barrier(2)

        def task():
            barrier.wait()
            results.append(rm.can_take_trade(acct, _signal()))

        threads = [threading.Thread(target=task) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            peak_concurrent[0], 1,
            f"Lock violated — {peak_concurrent[0]} threads inside simultaneously",
        )
        self.assertEqual(len(results), 2)


class TestDLLHardStop(unittest.TestCase):

    def test_dll_hard_stop_at_80_pct(self):
        """PROTECTED account that has used 80%+ of DLL must be blocked at halt_level 4."""
        rm = RiskManager()
        acct = _account(daily_pnl=-800.0, dll=1000.0)
        result = rm.can_take_trade(acct, _signal())
        self.assertFalse(result.allowed)
        self.assertEqual(result.halt_level, 4)


class TestUnrealizedPnL(unittest.TestCase):

    def test_unrealized_pnl_included_in_exposure(self):
        """get_total_exposure() must combine realized daily_pnl with unrealized position P&L."""
        rm = RiskManager()
        rm.daily_pnl = -200.0
        positions = [
            {
                "instrument": "MES",
                "current_price": 5300.0,
                "entry_price": 5310.0,
                "contracts": 1,
                "direction": "LONG",
            }
        ]
        # MES LONG unrealized: (5300 - 5310) * 5.0 * 1 = -50.0
        # Total expected: -200.0 + -50.0 = -250.0
        self.assertAlmostEqual(rm.get_total_exposure(positions), -250.0)


class TestSessionLimit(unittest.TestCase):

    def test_session_limit_blocks_excess_trades(self):
        """can_take_trade() must block when the current session's trade limit is exhausted."""
        rm = RiskManager()
        rm.session_trades["NY_OPEN"] = SESSION_TRADE_LIMITS["NY_OPEN"]

        with patch.object(rm, "_get_ict_session", return_value="NY_OPEN"):
            result = rm.can_take_trade(_account(), _signal())

        self.assertFalse(result.allowed)
        self.assertIn("Session limit", result.reason)
        self.assertIn("NY_OPEN", result.reason)


class TestDailyReset(unittest.TestCase):

    def test_protected_account_halts_after_day_end(self):
        """reset_daily() must set is_trading_halted=True and a /resume message for PROTECTED accounts."""
        rm = RiskManager()
        rm.reset_daily(_account(risk_mode="PROTECTED"))
        self.assertTrue(rm.is_trading_halted)
        self.assertIn("resume", rm.halt_reason.lower())

    def test_non_protected_account_auto_resumes_after_reset(self):
        """reset_daily() must leave is_trading_halted=False for non-PROTECTED accounts."""
        rm = RiskManager()
        rm.reset_daily(_account(risk_mode="BALANCED"))
        self.assertFalse(rm.is_trading_halted)


if __name__ == "__main__":
    unittest.main()
