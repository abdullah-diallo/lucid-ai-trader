"use client";

import { useQuery, useMutation } from "convex/react";
import { useUser } from "@clerk/nextjs";
import { api } from "@/convex/_generated/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Zap, ArrowLeftRight, LineChart, BarChart3, FlaskConical, MessageSquare, Pause, Play,
} from "lucide-react";

type View = "dashboard" | "strategies" | "brokers" | "tradingview" | "performance" | "backtest" | "chat";

const NAV_ITEMS: { view: View; label: string; icon: React.ElementType }[] = [
  { view: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { view: "strategies", label: "Strategies", icon: Zap },
  { view: "brokers", label: "Brokers", icon: ArrowLeftRight },
  { view: "tradingview", label: "Chart", icon: LineChart },
  { view: "performance", label: "Performance", icon: BarChart3 },
  { view: "backtest", label: "Backtest", icon: FlaskConical },
  { view: "chat", label: "AI Chat", icon: MessageSquare },
];

interface Props {
  activeView: View;
  onViewChange: (view: View) => void;
}

export function Sidebar({ activeView, onViewChange }: Props) {
  const { user } = useUser();
  const userId = user?.id ?? "";

  const state = useQuery(api.tradingState.get, userId ? { userId } : "skip");
  const pnlStats = useQuery(api.trades.getPnlStats, userId ? { userId, dateRange: "today" } : "skip");
  const setPaused = useMutation(api.tradingState.setPaused);

  const isPaused = state?.isPaused ?? false;

  return (
    <aside className="w-56 flex-none bg-card border-r border-border flex flex-col py-4 gap-1">
      {/* P&L Summary */}
      <div className="px-3 mb-2">
        <div className="glass rounded-xl p-3 space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Net P&L</span>
            <span className={cn("font-semibold tabular-nums", (pnlStats?.netPnl ?? 0) >= 0 ? "text-buy" : "text-sell")}>
              {(pnlStats?.netPnl ?? 0) >= 0 ? "+" : ""}${(pnlStats?.netPnl ?? 0).toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Win Rate</span>
            <span className="font-medium">{((pnlStats?.winRate ?? 0) * 100).toFixed(0)}%</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Trades</span>
            <span className="font-medium">{pnlStats?.totalTrades ?? 0}</span>
          </div>
        </div>
      </div>

      {/* Nav Links */}
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ view, label, icon: Icon }) => (
          <button
            key={view}
            onClick={() => onViewChange(view)}
            className={cn(
              "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors text-left",
              activeView === view
                ? "bg-primary/15 text-primary font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            )}
          >
            <Icon className="w-4 h-4 flex-none" />
            {label}
          </button>
        ))}
      </nav>

      {/* Pause / Resume */}
      <div className="px-3 pt-2 border-t border-border">
        <Button
          variant={isPaused ? "default" : "secondary"}
          size="sm"
          className="w-full gap-2"
          onClick={() => userId && setPaused({ userId, isPaused: !isPaused })}
        >
          {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
          {isPaused ? "Resume Trading" : "Pause Trading"}
        </Button>
      </div>
    </aside>
  );
}
