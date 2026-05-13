"""
core/performance_engine.py
===========================
Strategy performance analytics against the Supabase `trades` table.
Pure data queries — no Telegram calls, no side effects.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from data.supabase_client import get_supabase

logger = logging.getLogger(__name__)

DateRange = Union[str, Tuple[str, str]]  # "today"|"week"|"month"|"all" or ("2025-01-01","2025-03-31")


def _date_filter(date_range: DateRange) -> Tuple[Optional[str], Optional[str]]:
    """Return (gte_date, lte_date) ISO strings or (None, None) for all-time."""
    now  = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    if isinstance(date_range, tuple):
        return date_range[0], date_range[1]

    dr = str(date_range).lower()
    if dr == "today":
        return today, None
    if dr == "week":
        start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return start, None
    if dr == "month":
        start = now.strftime("%Y-%m-01")
        return start, None
    return None, None  # "all"


def _compute_streaks(results: List[bool]) -> Dict[str, int]:
    """
    Given a list of bool (True=win, False=loss, most-recent last),
    return current streak (positive=win streak, negative=loss streak) and max win/loss streaks.
    """
    if not results:
        return {"current": 0, "max_win": 0, "max_loss": 0}

    current = 1
    direction = 1 if results[-1] else -1
    for i in range(len(results) - 2, -1, -1):
        if bool(results[i]) == bool(results[-1]):
            current += 1
        else:
            break
    current_streak = current * direction

    max_win = max_loss = cur_w = cur_l = 0
    for r in results:
        if r:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        max_win  = max(max_win,  cur_w)
        max_loss = max(max_loss, cur_l)

    return {"current": current_streak, "max_win": max_win, "max_loss": max_loss}


class StrategyPerformanceEngine:
    """
    Queries the `trades` table and computes per-strategy statistics.
    All methods are safe to call with missing/empty data.
    """

    def get_strategy_stats(
        self,
        strategy_name: str,
        date_range: DateRange = "all",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return full stats dict for a single strategy."""
        trades = self._fetch_trades(strategy_name, date_range, user_id)

        if not trades:
            return self._empty_stats(strategy_name)

        pnl_values = [float(t.get("pnl", 0)) for t in trades]
        wins       = [p for p in pnl_values if p > 0]
        losses     = [p for p in pnl_values if p <= 0]

        total   = len(pnl_values)
        n_wins  = len(wins)
        n_loss  = len(losses)
        win_rate = n_wins / total * 100 if total else 0.0

        total_pnl    = sum(pnl_values)
        avg_win      = sum(wins) / len(wins)    if wins   else 0.0
        avg_loss     = sum(losses) / len(losses) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        results   = [p > 0 for p in pnl_values]  # oldest → newest
        streaks   = _compute_streaks(results)
        last_10   = results[-10:]

        # is_underperforming: win_rate < 40% over last 20 trades
        last_20   = results[-20:]
        under     = (sum(last_20) / len(last_20) * 100 < 40) if len(last_20) >= 5 else False

        # performance_trend: compare last 10 vs prior 10
        prior_10  = results[-20:-10]
        if len(last_10) >= 5 and len(prior_10) >= 5:
            last_wr  = sum(last_10)  / len(last_10)
            prior_wr = sum(prior_10) / len(prior_10)
            if last_wr >= prior_wr + 0.05:
                trend = "IMPROVING"
            elif last_wr <= prior_wr - 0.05:
                trend = "DECLINING"
            else:
                trend = "STABLE"
        else:
            trend = "STABLE"

        # Expectancy = (avg_win × win_rate) − (avg_loss × loss_rate)
        win_rate_frac = n_wins / total
        loss_rate_frac = 1 - win_rate_frac
        expectancy = (avg_win * win_rate_frac) - (abs(avg_loss) * loss_rate_frac)

        # Kill-zone split win rates
        def _wins_in(subset: List[Dict]) -> int:
            return sum(1 for t in subset if float(t.get("pnl", 0)) > 0)

        kz_trades     = [t for t in trades if t.get("kill_zone")]
        non_kz_trades = [t for t in trades if not t.get("kill_zone")]
        kill_zone_win_rate = (
            round(_wins_in(kz_trades) / len(kz_trades) * 100, 1) if kz_trades else None
        )
        non_kz_win_rate = (
            round(_wins_in(non_kz_trades) / len(non_kz_trades) * 100, 1) if non_kz_trades else None
        )

        # Confidence-tier split win rates
        high_conf = [t for t in trades if t.get("confidence", 0) >= 0.80]
        low_conf  = [t for t in trades if 0.65 <= t.get("confidence", 0) < 0.80]
        high_conf_win_rate = (
            round(_wins_in(high_conf) / len(high_conf) * 100, 1) if high_conf else None
        )
        low_conf_win_rate = (
            round(_wins_in(low_conf) / len(low_conf) * 100, 1) if low_conf else None
        )

        # Best and worst trades
        best_idx  = pnl_values.index(max(pnl_values))
        worst_idx = pnl_values.index(min(pnl_values))

        def _trade_date(t):
            return (t.get("closed_at") or t.get("opened_at") or "")[:10]

        return {
            "strategy_name":          strategy_name,
            "strategy_full_name":     trades[0].get("strategy_name", strategy_name) if trades else strategy_name,
            "total_trades":           total,
            "winning_trades":         n_wins,
            "losing_trades":          n_loss,
            "win_rate_pct":           round(win_rate, 1),
            "total_pnl":              round(total_pnl, 2),
            "average_win":            round(avg_win, 2),
            "average_loss":           round(avg_loss, 2),
            "profit_factor":          round(profit_factor, 2) if profit_factor != float("inf") else 999,
            "expectancy":             round(expectancy, 2),
            "best_trade_pnl":         round(max(pnl_values), 2),
            "worst_trade_pnl":        round(min(pnl_values), 2),
            "best_trade_date":        _trade_date(trades[best_idx]),
            "worst_trade_date":       _trade_date(trades[worst_idx]),
            "current_streak":         streaks["current"],
            "max_win_streak_ever":    streaks["max_win"],
            "max_loss_streak_ever":   streaks["max_loss"],
            "is_underperforming":     under,
            "performance_trend":      trend,
            "last_10_trades":         last_10,
            "kill_zone_win_rate":     kill_zone_win_rate,
            "non_kz_win_rate":        non_kz_win_rate,
            "high_conf_win_rate":     high_conf_win_rate,
            "low_conf_win_rate":      low_conf_win_rate,
            "kill_zone_trades":       len(kz_trades),
            "high_conf_trades":       len(high_conf),
            "low_conf_trades":        len(low_conf),
        }

    def get_all_strategies_report(
        self,
        date_range: DateRange = "all",
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stats for every strategy that has trades, sorted by total_pnl desc."""
        sb = get_supabase()
        try:
            query = sb.table("trades").select("strategy_name").eq("status", "closed")
            if user_id:
                query = query.eq("user_id", user_id)
            gte, lte = _date_filter(date_range)
            if gte:
                query = query.gte("closed_at", gte)
            if lte:
                query = query.lte("closed_at", lte)
            res = query.execute()
            names = {r["strategy_name"] for r in (res.data or []) if r.get("strategy_name")}
        except Exception:
            logger.exception("Failed to fetch strategy names.")
            names = set()

        results = []
        for name in names:
            results.append(self.get_strategy_stats(name, date_range, user_id))

        return sorted(results, key=lambda s: s["total_pnl"], reverse=True)

    def format_telegram_performance_report(self, stats: Dict[str, Any]) -> str:
        """Single-strategy Telegram-formatted report."""
        name  = stats.get("strategy_full_name", stats.get("strategy_name", "?"))
        trend_emoji = {"IMPROVING": "📈", "DECLINING": "📉", "STABLE": "➡️"}.get(
            stats.get("performance_trend", "STABLE"), "➡️"
        )
        under_note = " ⚠️ UNDERPERFORMING" if stats.get("is_underperforming") else ""

        last_10 = stats.get("last_10_trades", [])
        dots = "".join("🟢" if w else "🔴" for w in last_10) if last_10 else "—"

        return (
            f"📊 *{name}*{under_note}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Total trades: {stats.get('total_trades', 0)}\n"
            f"Win rate:     {stats.get('win_rate_pct', 0)}%\n"
            f"Total P&L:    ${stats.get('total_pnl', 0):+.2f}\n"
            f"Avg win:      ${stats.get('average_win', 0):+.2f}\n"
            f"Avg loss:     ${stats.get('average_loss', 0):.2f}\n"
            f"Profit factor:{stats.get('profit_factor', 0)}\n"
            f"Streak:       {stats.get('current_streak', 0):+d}\n"
            f"Trend:        {trend_emoji} {stats.get('performance_trend', 'STABLE')}\n"
            f"Last 10:      {dots}\n"
        )

    def format_all_strategies_telegram(
        self, strategies: List[Dict[str, Any]], date_range: DateRange = "all"
    ) -> str:
        """Full performance report for all strategies."""
        if not strategies:
            return "📊 No closed trades found for the selected period."

        total_pnl  = sum(s["total_pnl"] for s in strategies)
        total_wins = sum(s["winning_trades"] for s in strategies)
        total_all  = sum(s["total_trades"] for s in strategies)
        sys_wr     = total_wins / total_all * 100 if total_all else 0

        label_map  = {"today": "Today", "week": "This Week", "month": "This Month", "all": "All Time"}
        label      = label_map.get(str(date_range).lower(), str(date_range))

        lines = [
            f"📊 *PERFORMANCE REPORT — {label}*",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"💰 Total P&L: ${total_pnl:+.2f}",
            f"🎯 System Win Rate: {sys_wr:.0f}%",
        ]
        if strategies:
            best  = strategies[0]
            worst = strategies[-1]
            lines.append(
                f"📈 Best: {best['strategy_name']} "
                f"(${best['total_pnl']:+.2f} | {best['win_rate_pct']}% WR)"
            )
            lines.append(
                f"📉 Worst: {worst['strategy_name']} "
                f"(${worst['total_pnl']:+.2f} | {worst['win_rate_pct']}% WR)"
            )

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("STRATEGY BREAKDOWN:")

        for i, s in enumerate(strategies[:15], 1):
            warn = " ⚠️" if s.get("is_underperforming") else ""
            lines.append(
                f"{i}. {s['strategy_name']:<22} "
                f"${s['total_pnl']:+8.2f}  {s['win_rate_pct']:5.1f}% WR  "
                f"{s['total_trades']} trades{warn}"
            )

        if len(strategies) > 15:
            lines.append(f"… and {len(strategies) - 15} more")

        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_trades(
        self,
        strategy_name: str,
        date_range: DateRange,
        user_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        sb = get_supabase()
        try:
            query = (
                sb.table("trades")
                .select("*")
                .eq("status", "closed")
                .eq("strategy_name", strategy_name)
            )
            if user_id:
                query = query.eq("user_id", user_id)
            gte, lte = _date_filter(date_range)
            if gte:
                query = query.gte("closed_at", gte)
            if lte:
                query = query.lte("closed_at", lte)
            res = query.order("closed_at", desc=False).execute()
            return res.data or []
        except Exception:
            logger.exception("Failed to fetch trades for strategy %s.", strategy_name)
            return []

    @staticmethod
    def _empty_stats(strategy_name: str) -> Dict[str, Any]:
        return {
            "strategy_name":          strategy_name,
            "strategy_full_name":     strategy_name,
            "total_trades":           0,
            "winning_trades":         0,
            "losing_trades":          0,
            "win_rate_pct":           0.0,
            "total_pnl":              0.0,
            "average_win":            0.0,
            "average_loss":           0.0,
            "profit_factor":          0,
            "expectancy":             0.0,
            "best_trade_pnl":         0.0,
            "worst_trade_pnl":        0.0,
            "best_trade_date":        "",
            "worst_trade_date":       "",
            "current_streak":         0,
            "max_win_streak_ever":    0,
            "max_loss_streak_ever":   0,
            "is_underperforming":     False,
            "performance_trend":      "STABLE",
            "last_10_trades":         [],
            "kill_zone_win_rate":     None,
            "non_kz_win_rate":        None,
            "high_conf_win_rate":     None,
            "low_conf_win_rate":      None,
            "kill_zone_trades":       0,
            "high_conf_trades":       0,
            "low_conf_trades":        0,
        }
