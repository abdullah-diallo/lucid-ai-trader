"use client";

import { useQuery } from "convex/react";
import { useUser } from "@clerk/nextjs";
import { api } from "@/convex/_generated/api";
import { STRATEGY_REGISTRY } from "@/convex/strategies";
import { cn } from "@/lib/utils";
import { useState } from "react";

type DateRange = "today" | "week" | "month" | "all";

const DATE_RANGES: { label: string; value: DateRange }[] = [
  { label: "Today", value: "today" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
  { label: "All Time", value: "all" },
];

export function PerformanceView() {
  const { user } = useUser();
  const userId = user?.id ?? "";
  const [dateRange, setDateRange] = useState<DateRange>("week");

  const pnl = useQuery(api.trades.getPnlStats, userId ? { userId, dateRange } : "skip");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Performance</h2>
        <div className="flex gap-1">
          {DATE_RANGES.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setDateRange(value)}
              className={cn("px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                dateRange === value ? "bg-primary text-white" : "bg-white/5 text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Net P&L", value: `${(pnl?.netPnl ?? 0) >= 0 ? "+" : ""}$${(pnl?.netPnl ?? 0).toFixed(2)}`, color: (pnl?.netPnl ?? 0) >= 0 ? "text-buy" : "text-sell" },
          { label: "Win Rate", value: `${((pnl?.winRate ?? 0) * 100).toFixed(1)}%`, color: "text-foreground" },
          { label: "Profit Factor", value: (pnl?.profitFactor ?? 0).toFixed(2), color: (pnl?.profitFactor ?? 0) >= 1.5 ? "text-buy" : "text-sell" },
          { label: "Total Trades", value: String(pnl?.totalTrades ?? 0), color: "text-foreground" },
        ].map(({ label, value, color }) => (
          <div key={label} className="glass rounded-2xl p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={cn("text-xl font-bold tabular-nums mt-1", color)}>{value}</p>
          </div>
        ))}
      </div>

      {/* Strategy Table */}
      <div className="glass rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold">Strategy Breakdown</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-3 text-xs text-muted-foreground font-medium">Strategy</th>
                <th className="text-right px-4 py-3 text-xs text-muted-foreground font-medium">Trades</th>
                <th className="text-right px-4 py-3 text-xs text-muted-foreground font-medium">Win Rate</th>
                <th className="text-right px-4 py-3 text-xs text-muted-foreground font-medium">Net P&L</th>
              </tr>
            </thead>
            <tbody>
              {STRATEGY_REGISTRY.slice(0, 10).map((s) => (
                <StrategyRow key={s.id} userId={userId} strategyId={s.id} name={s.name} dateRange={dateRange} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StrategyRow({ userId, strategyId, name, dateRange }: { userId: string; strategyId: string; name: string; dateRange: DateRange }) {
  const stats = useQuery(api.trades.getByStrategy, userId ? { userId, strategy: strategyId, dateRange } : "skip");

  if (!stats || stats.totalTrades === 0) return null;

  return (
    <tr className="border-b border-border/50 hover:bg-white/3 transition-colors">
      <td className="px-4 py-2.5 font-medium">{name}</td>
      <td className="px-4 py-2.5 text-right text-muted-foreground">{stats.totalTrades}</td>
      <td className="px-4 py-2.5 text-right">{((stats.winRate ?? 0) * 100).toFixed(0)}%</td>
      <td className={cn("px-4 py-2.5 text-right font-semibold tabular-nums", (stats.netPnl ?? 0) >= 0 ? "text-buy" : "text-sell")}>
        {(stats.netPnl ?? 0) >= 0 ? "+" : ""}${(stats.netPnl ?? 0).toFixed(2)}
      </td>
    </tr>
  );
}
