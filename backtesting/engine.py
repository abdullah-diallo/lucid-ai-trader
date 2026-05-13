"""
backtesting/engine.py
=====================
Runs a strategy against historical OHLCV data and returns full results:
equity curve, trade list, and performance metrics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backtesting.data_fetcher import fetch_ohlcv
from backtesting.strategies import BACKTEST_STRATEGIES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Core simulation ────────────────────────────────────────────────────────────

def _simulate(df: pd.DataFrame, signals: List[Dict], starting_balance: float, qty: int) -> Dict[str, Any]:
    """
    Walk through signals and simulate fills.
    Returns trades list and equity-over-time list.
    """
    balance     = starting_balance
    position    = 0       # +qty = long, -qty = short, 0 = flat
    entry_price = 0.0
    trades: List[Dict] = []
    equity: List[Dict] = []

    # Snapshot equity at every bar
    bar_equities = [starting_balance] * len(df)

    for sig in signals:
        bar    = sig["bar"]
        price  = float(sig["price"])
        action = sig["action"]

        if action == "BUY" and position <= 0:
            if position < 0:  # close short first
                pnl = (entry_price - price) * abs(position)
                balance += pnl
                trades.append({
                    "entry_price": entry_price,
                    "exit_price":  price,
                    "side":        "Short",
                    "qty":         abs(position),
                    "pnl":         round(pnl, 2),
                    "entry_bar":   bar,
                    "exit_bar":    bar,
                    "reason":      sig.get("reason", ""),
                    "timestamp":   str(df.index[bar]),
                })
            position    = qty
            entry_price = price

        elif action == "SELL" and position >= 0:
            if position > 0:  # close long first
                pnl = (price - entry_price) * position
                balance += pnl
                trades.append({
                    "entry_price": entry_price,
                    "exit_price":  price,
                    "side":        "Long",
                    "qty":         position,
                    "pnl":         round(pnl, 2),
                    "entry_bar":   bar,
                    "exit_bar":    bar,
                    "reason":      sig.get("reason", ""),
                    "timestamp":   str(df.index[bar]),
                })
            position    = -qty
            entry_price = price

        elif action == "CLOSE" and position != 0:
            if position > 0:
                pnl  = (price - entry_price) * position
                side = "Long"
            else:
                pnl  = (entry_price - price) * abs(position)
                side = "Short"
            balance += pnl
            trades.append({
                "entry_price": entry_price,
                "exit_price":  price,
                "side":        side,
                "qty":         abs(position),
                "pnl":         round(pnl, 2),
                "entry_bar":   bar,
                "exit_bar":    bar,
                "reason":      sig.get("reason", ""),
                "timestamp":   str(df.index[bar]),
            })
            position = 0

        # Update equity for this bar onward
        if bar < len(bar_equities):
            unreal = 0.0
            if position != 0:
                close = float(df["close"].iloc[bar])
                unreal = (close - entry_price) * position if position > 0 else (entry_price - close) * abs(position)
            bar_equities[bar] = round(balance + unreal, 2)

    # Forward-fill equity for bars between signals
    last = starting_balance
    for i in range(len(bar_equities)):
        if bar_equities[i] != starting_balance or i == 0:
            last = bar_equities[i]
        else:
            bar_equities[i] = last

    equity = [
        {"time": str(df.index[i]), "equity": bar_equities[i]}
        for i in range(0, len(df), max(1, len(df) // 300))  # downsample to ≤300 pts
    ]

    return {"trades": trades, "equity": equity, "final_balance": round(balance, 2)}


# ── Metrics ────────────────────────────────────────────────────────────────────

def _metrics(trades: List[Dict], starting_balance: float, final_balance: float) -> Dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0, "total_pnl": 0,
            "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            "max_drawdown_pct": 0, "sharpe": 0,
        }

    pnls  = [t["pnl"] for t in trades]
    wins  = [p for p in pnls if p > 0]
    losses= [p for p in pnls if p <= 0]

    gross_profit = sum(wins)   if wins   else 0
    gross_loss   = abs(sum(losses)) if losses else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 999.0

    # Sharpe (annualised, assuming 252 trading days)
    pnl_arr = np.array(pnls, dtype=float)
    sharpe  = 0.0
    if len(pnl_arr) > 1 and pnl_arr.std() > 0:
        sharpe = round(float(pnl_arr.mean() / pnl_arr.std() * np.sqrt(252)), 2)

    # Max drawdown on running cumulative P&L
    cum   = np.cumsum(pnl_arr)
    peak  = np.maximum.accumulate(cum)
    dd    = (peak - cum) / (starting_balance + peak) * 100
    max_dd = round(float(dd.max()), 2) if len(dd) else 0.0

    return {
        "total_trades":     len(trades),
        "win_rate":         round(len(wins) / len(trades) * 100, 1),
        "total_pnl":        round(sum(pnls), 2),
        "avg_win":          round(sum(wins)   / len(wins)   if wins   else 0, 2),
        "avg_loss":         round(sum(losses) / len(losses) if losses else 0, 2),
        "profit_factor":    profit_factor,
        "max_drawdown_pct": max_dd,
        "sharpe":           sharpe,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def run_backtest(
    strategy_name: str,
    symbol: str,
    start: str,
    end: str,
    interval: str = "5m",
    starting_balance: float = 100_000.0,
    qty: int = 1,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Download data, run strategy, simulate fills, compute metrics.
    Returns a dict safe to JSON-serialise and send to the dashboard.
    """
    if strategy_name not in BACKTEST_STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy_name}'. "
                         f"Available: {list(BACKTEST_STRATEGIES)}")

    params = params or {}
    strat  = BACKTEST_STRATEGIES[strategy_name]

    # 1. Fetch data
    df = fetch_ohlcv(symbol, start, end, interval)

    # 2. Generate signals
    signals = strat["fn"](df, **params)

    # 3. Simulate
    sim = _simulate(df, signals, starting_balance, qty)

    # 4. Metrics
    metrics = _metrics(sim["trades"], starting_balance, sim["final_balance"])

    return {
        "id":               str(uuid.uuid4())[:8],
        "strategy":         strategy_name,
        "strategy_label":   strat["label"],
        "symbol":           symbol,
        "start":            start,
        "end":              end,
        "interval":         interval,
        "starting_balance": starting_balance,
        "final_balance":    sim["final_balance"],
        "bars_tested":      len(df),
        "trades":           sim["trades"],
        "equity":           sim["equity"],
        "metrics":          metrics,
        "ran_at":           _now_iso(),
    }


def list_strategies() -> List[Dict[str, Any]]:
    return [
        {
            "name":        v["name"],
            "label":       v["label"],
            "description": v["description"],
            "markets":     v["markets"],
        }
        for v in BACKTEST_STRATEGIES.values()
    ]
