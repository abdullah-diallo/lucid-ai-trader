"use client";

import { useState } from "react";
import { STRATEGY_REGISTRY } from "@/convex/strategies";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { BacktestResult } from "@/lib/types";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { FlaskConical } from "lucide-react";

export function BacktestView() {
  const [strategyId, setStrategyId] = useState("ORB");
  const [symbol, setSymbol] = useState("SPY");
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [balance, setBalance] = useState("100000");
  const [qty, setQty] = useState("1");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");

  async function runBacktest() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategyId, symbol, start, end, startingBalance: Number(balance), qty: Number(qty) }),
      });
      const data = await res.json();
      if (data.error) setError(data.error);
      else setResult(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setRunning(false);
    }
  }

  const equityData = result?.equityCurve.map((val, i) => ({ bar: i, equity: val })) ?? [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-full">
      {/* Form */}
      <div className="glass rounded-2xl p-4 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-primary" />
          Backtest Setup
        </h3>

        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">Strategy</label>
          <select
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {STRATEGY_REGISTRY.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        {[
          { label: "Symbol", value: symbol, setter: setSymbol, placeholder: "SPY, QQQ, MES1!" },
          { label: "Start Date", value: start, setter: setStart, type: "date" },
          { label: "End Date", value: end, setter: setEnd, type: "date" },
          { label: "Starting Balance ($)", value: balance, setter: setBalance, type: "number" },
          { label: "Contracts / Qty", value: qty, setter: setQty, type: "number" },
        ].map(({ label, value, setter, placeholder, type }) => (
          <div key={label} className="space-y-1">
            <label className="text-xs text-muted-foreground">{label}</label>
            <input
              type={type ?? "text"}
              value={value}
              onChange={(e) => setter(e.target.value)}
              placeholder={placeholder}
              className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        ))}

        <Button className="w-full" onClick={runBacktest} disabled={running}>
          {running ? "Running…" : "Run Backtest"}
        </Button>

        {error && <p className="text-xs text-sell">{error}</p>}
      </div>

      {/* Results */}
      <div className="lg:col-span-2 space-y-4">
        {result ? (
          <>
            {/* Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Net P&L", value: `$${result.metrics.netPnl.toFixed(2)}`, pos: result.metrics.netPnl >= 0 },
                { label: "Win Rate", value: `${(result.metrics.winRate * 100).toFixed(1)}%`, pos: result.metrics.winRate > 0.5 },
                { label: "Profit Factor", value: result.metrics.profitFactor.toFixed(2), pos: result.metrics.profitFactor >= 1 },
                { label: "Total Trades", value: String(result.metrics.totalTrades), pos: true },
              ].map(({ label, value, pos }) => (
                <div key={label} className="glass rounded-xl p-3">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className={cn("text-lg font-bold tabular-nums mt-1", pos ? "text-buy" : "text-sell")}>{value}</p>
                </div>
              ))}
            </div>

            {/* Equity Curve */}
            <div className="glass rounded-2xl p-4">
              <h3 className="text-sm font-semibold mb-3">Equity Curve</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={equityData}>
                  <XAxis dataKey="bar" hide />
                  <YAxis domain={["auto", "auto"]} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, "Equity"]} />
                  <Line type="monotone" dataKey="equity" stroke="#0A84FF" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Trades Table */}
            <div className="glass rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h3 className="text-sm font-semibold">Trades ({result.trades.length})</h3>
              </div>
              <div className="overflow-x-auto max-h-48">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      {["Side", "Entry", "Exit", "P&L"].map((h) => (
                        <th key={h} className="text-left px-4 py-2 text-muted-foreground font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(-20).reverse().map((t, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className={cn("px-4 py-2 font-medium", t.side === "Long" ? "text-buy" : "text-sell")}>{t.side}</td>
                        <td className="px-4 py-2 tabular-nums">{t.entryPrice.toFixed(2)}</td>
                        <td className="px-4 py-2 tabular-nums">{t.exitPrice.toFixed(2)}</td>
                        <td className={cn("px-4 py-2 tabular-nums font-semibold", t.pnl >= 0 ? "text-buy" : "text-sell")}>
                          {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : (
          <div className="glass rounded-2xl p-12 flex items-center justify-center">
            <p className="text-muted-foreground text-sm">Configure and run a backtest to see results</p>
          </div>
        )}
      </div>
    </div>
  );
}
