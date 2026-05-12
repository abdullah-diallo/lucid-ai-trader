"use client";

import { useQuery, useMutation } from "convex/react";
import { useUser } from "@clerk/nextjs";
import { api } from "@/convex/_generated/api";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Activity, DollarSign, Send } from "lucide-react";

function PnlCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-2xl font-bold tabular-nums", color)}>{value}</span>
    </div>
  );
}

export function DashboardView() {
  const { user } = useUser();
  const userId = user?.id ?? "";

  const pnl = useQuery(api.trades.getPnlStats, userId ? { userId, dateRange: "today" } : "skip");
  const signals = useQuery(api.signals.list, userId ? { userId, limit: 20 } : "skip");
  const state = useQuery(api.tradingState.get, userId ? { userId } : "skip");
  const [symbol, setSymbol] = useState("MES1!");
  const [action, setAction] = useState<"BUY" | "SELL" | "CLOSE">("BUY");
  const [manualReason, setManualReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submitManual() {
    setSubmitting(true);
    try {
      await fetch("/api/trade/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, action, reason: manualReason }),
      });
      setManualReason("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* P&L Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <PnlCard label="Net P&L" value={`${(pnl?.netPnl ?? 0) >= 0 ? "+" : ""}$${(pnl?.netPnl ?? 0).toFixed(2)}`} color={(pnl?.netPnl ?? 0) >= 0 ? "text-buy" : "text-sell"} />
        <PnlCard label="Win Rate" value={`${((pnl?.winRate ?? 0) * 100).toFixed(0)}%`} color="text-foreground" />
        <PnlCard label="Gross Profit" value={`$${(pnl?.grossProfit ?? 0).toFixed(2)}`} color="text-buy" />
        <PnlCard label="Gross Loss" value={`-$${(pnl?.grossLoss ?? 0).toFixed(2)}`} color="text-sell" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Signals Feed */}
        <div className="lg:col-span-2 glass rounded-2xl p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent" />
            Recent Signals
          </h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {(signals ?? []).length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-8">No signals yet</p>
            )}
            {(signals ?? []).map((s) => (
              <div key={s._id} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/3 hover:bg-white/5 transition-colors">
                <Badge
                  variant="outline"
                  className={cn("text-xs border",
                    s.action === "BUY" ? "text-buy border-buy/30 bg-buy/10" :
                    s.action === "SELL" ? "text-sell border-sell/30 bg-sell/10" :
                    "text-close border-close/30 bg-close/10"
                  )}
                >
                  {s.action}
                </Badge>
                <span className="text-sm font-medium">{s.symbol}</span>
                <span className="text-xs text-muted-foreground flex-1">{s.reason}</span>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full",
                  s.status === "executed" ? "bg-buy/10 text-buy" :
                  s.status === "filtered" ? "bg-muted text-muted-foreground" :
                  "bg-close/10 text-close"
                )}>
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Manual Trade + Mode */}
        <div className="space-y-3">
          <div className="glass rounded-2xl p-4">
            <h3 className="text-sm font-semibold mb-3">Manual Trade</h3>
            <div className="space-y-2">
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="Symbol (MES1!)"
                className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <div className="grid grid-cols-3 gap-1">
                {(["BUY", "SELL", "CLOSE"] as const).map((a) => (
                  <button
                    key={a}
                    onClick={() => setAction(a)}
                    className={cn("py-1.5 rounded-lg text-xs font-semibold transition-colors",
                      action === a ? (a === "BUY" ? "bg-buy text-white" : a === "SELL" ? "bg-sell text-white" : "bg-close text-white") :
                      "bg-white/5 text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {a}
                  </button>
                ))}
              </div>
              <input
                value={manualReason}
                onChange={(e) => setManualReason(e.target.value)}
                placeholder="Reason (optional)"
                className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <Button className="w-full gap-2" onClick={submitManual} disabled={submitting}>
                <Send className="w-3.5 h-3.5" />
                {submitting ? "Submitting…" : "Submit"}
              </Button>
            </div>
          </div>

          <div className="glass rounded-2xl p-4">
            <h3 className="text-sm font-semibold mb-2">Trading Mode</h3>
            <p className="text-sm font-medium text-primary">{state?.mode ?? "FULL_AUTO"}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {state?.isPaused ? "⏸ Trading paused" : "▶ Trading active"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
