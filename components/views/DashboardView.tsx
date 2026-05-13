"use client";

import { useQuery, useMutation } from "convex/react";
import { useCurrentUserId } from "@/hooks/useCurrentUserId";
import { api } from "@/convex/_generated/api";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Activity, Send, CheckCircle2, XCircle, Clock, Bell } from "lucide-react";

function PnlCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-2xl font-bold tabular-nums", color)}>{value}</span>
    </div>
  );
}

function PendingApprovalBanner({
  userId,
}: {
  userId: string;
}) {
  const pendingSignal = useQuery(api.signals.getPending, userId ? { userId } : "skip");
  const updateStatus = useMutation(api.signals.updateStatus);
  const [countdown, setCountdown] = useState(90);

  useEffect(() => {
    if (!pendingSignal) return;
    setCountdown(90);
    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          updateStatus({ signalId: pendingSignal._id, status: "rejected" });
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingSignal?._id]);

  if (!pendingSignal) return null;

  return (
    <div className="glass border border-accent/40 rounded-2xl p-4 flex items-center gap-4 animate-pulse-subtle">
      <div className="flex items-center gap-2 text-accent flex-none">
        <Clock className="w-5 h-5" />
        <span className="text-2xl font-bold tabular-nums w-8">{countdown}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">Trade approval required</p>
        <p className="text-xs text-muted-foreground truncate">
          <span className={cn("font-medium", pendingSignal.action === "BUY" ? "text-buy" : "text-sell")}>
            {pendingSignal.action}
          </span>{" "}
          {pendingSignal.symbol} — {pendingSignal.reason}
        </p>
      </div>
      <div className="flex gap-2 flex-none">
        <Button
          size="sm"
          className="gap-1.5 bg-buy hover:bg-buy/90 text-white"
          onClick={() => updateStatus({ signalId: pendingSignal._id, status: "approved" })}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 border-sell/40 text-sell hover:bg-sell/10"
          onClick={() => updateStatus({ signalId: pendingSignal._id, status: "rejected" })}
        >
          <XCircle className="w-3.5 h-3.5" />
          Decline
        </Button>
      </div>
    </div>
  );
}

export function DashboardView() {
  const userId = useCurrentUserId();

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
        body: JSON.stringify({ userId, symbol, action, reason: manualReason }),
      });
      setManualReason("");
    } finally {
      setSubmitting(false);
    }
  }

  const modeLabel = {
    FULL_AUTO: "Auto Trading",
    SEMI_AUTO: "Pre-Approval",
    SIGNALS_ONLY: "Manual",
  }[state?.mode ?? "FULL_AUTO"];

  const modeDescription = {
    FULL_AUTO: "Bot enters trades automatically",
    SEMI_AUTO: "Bot asks you 90s before each trade",
    SIGNALS_ONLY: "Signals shown — you enter trades yourself",
  }[state?.mode ?? "FULL_AUTO"];

  return (
    <div className="space-y-4">
      {/* Pre-approval banner */}
      {state?.mode === "SEMI_AUTO" && <PendingApprovalBanner userId={userId} />}

      {/* Manual mode: latest signal alert */}
      {state?.mode === "SIGNALS_ONLY" && signals && signals.length > 0 && (() => {
        const latest = signals[0];
        const age = Date.now() - latest.receivedAt;
        if (age > 60_000) return null;
        return (
          <div className="glass border border-primary/30 rounded-2xl p-4 flex items-center gap-3">
            <Bell className="w-4 h-4 text-primary flex-none" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">New signal — enter manually if you agree</p>
              <p className="text-xs text-muted-foreground truncate">
                <span className={cn("font-medium", latest.action === "BUY" ? "text-buy" : "text-sell")}>
                  {latest.action}
                </span>{" "}
                {latest.symbol} — {latest.reason}
              </p>
            </div>
            <span className="text-xs text-muted-foreground flex-none">
              {Math.round(age / 1000)}s ago
            </span>
          </div>
        );
      })()}

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
                <span className="text-xs text-muted-foreground flex-1 truncate">{s.reason}</span>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full",
                  s.status === "executed" ? "bg-buy/10 text-buy" :
                  s.status === "pending" ? "bg-accent/10 text-accent" :
                  s.status === "rejected" ? "bg-sell/10 text-sell" :
                  "bg-muted text-muted-foreground"
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
            <p className="text-sm font-medium text-primary">{modeLabel}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{modeDescription}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {state?.isPaused ? "⏸ Trading paused" : "▶ Trading active"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
