"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Copy, ExternalLink, Webhook, FlaskConical, RefreshCw, Power } from "lucide-react";

function getWebhookUrl() {
  if (typeof window === "undefined") return "http://localhost:8080/api/webhook/tradingview";
  return `${window.location.origin}/api/webhook/tradingview`;
}

interface PaperStatus {
  connected: boolean;
  balance: number;
  startingBalance: number;
  positions: { symbol: string; qty: number; side: string; entryPrice: number; currentPnl: number }[];
}

export function BrokersView() {
  const [copied, setCopied] = useState(false);
  const [paper, setPaper] = useState<PaperStatus | null>(null);
  const [balanceInput, setBalanceInput] = useState("");
  const [loading, setLoading] = useState<string | null>(null);

  async function fetchPaper() {
    const data = await fetch("/api/brokers/paper").then((r) => r.json()).catch(() => null);
    if (data) {
      setPaper(data);
      setBalanceInput(String(data.startingBalance));
    }
  }

  useEffect(() => { fetchPaper(); }, []);

  async function paperAction(action: string, body?: Record<string, unknown>) {
    setLoading(action);
    await fetch(`/api/brokers/paper?action=${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    await fetchPaper();
    setLoading(null);
  }

  function copyWebhook() {
    navigator.clipboard.writeText(getWebhookUrl());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const pnl = paper ? paper.balance - paper.startingBalance : 0;

  return (
    <div className="space-y-4 max-w-2xl">
      <h2 className="text-lg font-semibold">Trading Accounts</h2>

      {/* TradingView */}
      <div className="glass rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Webhook className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <p className="font-medium text-sm">TradingView</p>
              <p className="text-xs text-muted-foreground">Connect your TradingView alerts to auto-trade</p>
            </div>
          </div>
          <Badge variant="outline" className="text-buy border-buy/30 bg-buy/10 text-xs">Active</Badge>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs text-muted-foreground">Your webhook URL</label>
            <span className="text-xs text-accent">Copy → paste into TradingView alert</span>
          </div>
          <div className="flex gap-2">
            <code className="flex-1 bg-black/30 border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground truncate">
              {getWebhookUrl()}
            </code>
            <Button size="sm" variant="outline" onClick={copyWebhook} className="gap-1.5 shrink-0">
              <Copy className="w-3.5 h-3.5" />
              {copied ? "Copied!" : "Copy"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            No need to type anything — just copy the URL above and paste it in TradingView&apos;s alert webhook field.
          </p>
        </div>

        <div className="bg-white/3 rounded-xl p-4 space-y-2">
          <p className="text-xs font-medium">How to connect in TradingView</p>
          <ol className="text-xs text-muted-foreground space-y-1.5 list-decimal list-inside">
            <li>Open TradingView → go to your chart</li>
            <li>Click <span className="text-foreground font-medium">Alerts</span> → Create alert on your strategy</li>
            <li>Paste the webhook URL above into the <span className="text-foreground font-medium">Webhook URL</span> field</li>
            <li>Set alert message to: <code className="bg-black/30 px-1 rounded">{"{{strategy.order.action}}"}</code></li>
            <li>Save — signals will now flow to the bot automatically</li>
          </ol>
        </div>

        <Button variant="outline" size="sm" className="w-full gap-2"
          onClick={() => window.open("https://www.tradingview.com", "_blank")}>
          <ExternalLink className="w-3.5 h-3.5" />
          Open TradingView
        </Button>
      </div>

      {/* Paper Trading */}
      <div className="glass rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center">
              <FlaskConical className="w-4 h-4 text-orange-400" />
            </div>
            <div>
              <p className="font-medium text-sm">Paper Trading</p>
              <p className="text-xs text-muted-foreground">Simulated account — no real money</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline"
              className={cn("text-xs", paper?.connected
                ? "text-buy border-buy/30 bg-buy/10"
                : "text-muted-foreground border-border")}>
              {paper?.connected ? "Connected" : "Disconnected"}
            </Badge>
            <Button
              size="sm"
              variant={paper?.connected ? "secondary" : "default"}
              className="gap-1.5 h-7 px-2.5 text-xs"
              onClick={() => paperAction(paper?.connected ? "disconnect" : "connect")}
              disabled={loading !== null}
            >
              <Power className="w-3 h-3" />
              {paper?.connected ? "Disconnect" : "Connect"}
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white/3 rounded-xl p-3">
            <p className="text-xs text-muted-foreground">Balance</p>
            <p className="text-base font-bold tabular-nums">${(paper?.balance ?? 100000).toLocaleString()}</p>
          </div>
          <div className="bg-white/3 rounded-xl p-3">
            <p className="text-xs text-muted-foreground">Starting</p>
            <p className="text-base font-bold tabular-nums">${(paper?.startingBalance ?? 100000).toLocaleString()}</p>
          </div>
          <div className="bg-white/3 rounded-xl p-3">
            <p className="text-xs text-muted-foreground">P&L</p>
            <p className={cn("text-base font-bold tabular-nums", pnl >= 0 ? "text-buy" : "text-sell")}>
              {pnl >= 0 ? "+" : ""}${pnl.toLocaleString()}
            </p>
          </div>
        </div>

        {/* Set Balance */}
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Set account balance</label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
              <input
                type="number"
                value={balanceInput}
                onChange={(e) => setBalanceInput(e.target.value)}
                className="w-full bg-input border border-border rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                placeholder="100000"
                min={1000}
              />
            </div>
            <Button
              size="sm"
              onClick={() => paperAction("set-balance", { balance: Number(balanceInput) })}
              disabled={loading !== null || !balanceInput || Number(balanceInput) <= 0}
            >
              Set Balance
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">This resets the account to the new balance and clears all positions.</p>
        </div>

        {/* Positions */}
        {(paper?.positions ?? []).length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Open Positions</p>
            <div className="space-y-1">
              {paper!.positions.map((p) => (
                <div key={p.symbol} className="flex items-center justify-between bg-white/3 rounded-lg px-3 py-2 text-xs">
                  <span className="font-medium">{p.symbol}</span>
                  <span className={cn("font-medium", p.side === "Long" ? "text-buy" : "text-sell")}>{p.side}</span>
                  <span className="text-muted-foreground">Qty {p.qty}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Reset */}
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-2 border-sell/30 text-sell hover:bg-sell/10"
          onClick={() => paperAction("reset")}
          disabled={loading !== null}
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {loading === "reset" ? "Resetting…" : "Reset Account"}
        </Button>
      </div>
    </div>
  );
}
