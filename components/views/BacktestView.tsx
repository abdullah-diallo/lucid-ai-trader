"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { STRATEGY_REGISTRY } from "@/convex/strategies";
import { Button } from "@/components/ui/button";
import type { BacktestResult } from "@/lib/types";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { FlaskConical } from "lucide-react";

// Only strategies that require session-time context are hidden from Daily
const INTRADAY_ONLY = new Set(["ORB", "ASIA_RANGE", "NEWS_SPIKE", "SCALPING"]);

const TIMEFRAMES = [
  { value: "1d", label: "Daily", note: "Any date range — best for swing strategies" },
  { value: "1h", label: "1-Hour", note: "Up to 2 years of data — works for all strategies" },
  { value: "15m", label: "15-Min", note: "Last 60 days max — best for intraday strategies" },
] as const;

type Timeframe = typeof TIMEFRAMES[number]["value"];

const TV_SYMBOLS = [
  { tv: "MES1!", label: "MES1! — Micro E-mini S&P 500" },
  { tv: "MNQ1!", label: "MNQ1! — Micro Nasdaq" },
  { tv: "M2K1!", label: "M2K1! — Micro Russell 2000" },
  { tv: "MYM1!", label: "MYM1! — Micro Dow Jones" },
  { tv: "MGC1!", label: "MGC1! — Micro Gold" },
  { tv: "MCL1!", label: "MCL1! — Micro Crude Oil" },
  { tv: "ES1!", label: "ES1! — E-mini S&P 500" },
  { tv: "NQ1!", label: "NQ1! — Nasdaq Futures" },
  { tv: "RTY1!", label: "RTY1! — Russell 2000 Futures" },
  { tv: "YM1!", label: "YM1! — Dow Jones Futures" },
  { tv: "GC1!", label: "GC1! — Gold Futures" },
  { tv: "SI1!", label: "SI1! — Silver Futures" },
  { tv: "CL1!", label: "CL1! — Crude Oil Futures" },
  { tv: "NG1!", label: "NG1! — Natural Gas" },
  { tv: "ZB1!", label: "ZB1! — 30Y Treasury Bond" },
  { tv: "ZN1!", label: "ZN1! — 10Y Treasury Note" },
  { tv: "SPY", label: "SPY — S&P 500 ETF" },
  { tv: "QQQ", label: "QQQ — Nasdaq ETF" },
  { tv: "AAPL", label: "AAPL — Apple" },
  { tv: "TSLA", label: "TSLA — Tesla" },
  { tv: "NVDA", label: "NVDA — Nvidia" },
  { tv: "MSFT", label: "MSFT — Microsoft" },
  { tv: "AMZN", label: "AMZN — Amazon" },
  { tv: "EURUSD", label: "EURUSD — Euro / USD" },
  { tv: "GBPUSD", label: "GBPUSD — GBP / USD" },
  { tv: "USDJPY", label: "USDJPY — USD / JPY" },
];

function defaultDates(tf: Timeframe): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  if (tf === "15m") {
    start.setDate(start.getDate() - 55);
  } else if (tf === "1h") {
    start.setFullYear(start.getFullYear() - 1);
  } else {
    start.setFullYear(start.getFullYear() - 1);
  }
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

export function BacktestView() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [strategyId, setStrategyId] = useState("BREAKOUT");
  const [symbol, setSymbol] = useState("MES1!");
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [balance, setBalance] = useState("100000");
  const [qty, setQty] = useState("1");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");

  const availableStrategies = timeframe === "1d"
    ? STRATEGY_REGISTRY.filter((s) => !INTRADAY_ONLY.has(s.id))
    : STRATEGY_REGISTRY;

  function handleTimeframeChange(tf: Timeframe) {
    setTimeframe(tf);
    setResult(null);
    setError("");
    const dates = defaultDates(tf);
    setStart(dates.start);
    setEnd(dates.end);
    // Only reset if current strategy isn't available on the new timeframe
    if (tf === "1d" && INTRADAY_ONLY.has(strategyId)) {
      setStrategyId("BREAKOUT");
    }
  }

  async function runBacktest() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategyId, symbol, start, end, startingBalance: Number(balance), qty: Number(qty), timeframe }),
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
  const tfMeta = TIMEFRAMES.find((t) => t.value === timeframe)!;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-full">
      {/* Form */}
      <div className="glass rounded-2xl p-4 space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-primary" />
          Backtest Setup
        </h3>

        {/* Timeframe selector */}
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Timeframe</label>
          <div className="grid grid-cols-3 gap-1">
            {TIMEFRAMES.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => handleTimeframeChange(value)}
                className={cn(
                  "py-1.5 rounded-lg text-xs font-semibold transition-colors",
                  timeframe === value
                    ? "bg-primary text-white"
                    : "bg-white/5 text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{tfMeta.note}</p>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">
            Strategy <span className="text-muted-foreground/60">— {availableStrategies.length} available</span>
          </label>
          <div className="max-h-44 overflow-y-auto space-y-0.5 pr-0.5 scrollbar-thin">
            {availableStrategies.map((s) => (
              <button
                key={s.id}
                onClick={() => setStrategyId(s.id)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-lg transition-colors",
                  strategyId === s.id
                    ? "bg-primary/20 border border-primary/40 text-foreground"
                    : "bg-white/3 border border-transparent text-muted-foreground hover:text-foreground hover:bg-white/5"
                )}
              >
                <p className="text-xs font-semibold leading-tight">{s.name}</p>
                <p className="text-xs opacity-50 leading-tight mt-0.5 truncate">{s.description}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Symbol</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-input border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {TV_SYMBOLS.map(({ tv, label }) => (
              <option key={tv} value={tv}>{label}</option>
            ))}
          </select>
        </div>

        {[
          { label: "Start Date", value: start, setter: setStart, type: "date" },
          { label: "End Date", value: end, setter: setEnd, type: "date" },
          { label: "Starting Balance ($)", value: balance, setter: setBalance, type: "number" },
          { label: "Contracts / Qty", value: qty, setter: setQty, type: "number" },
        ].map(({ label, value, setter, type }) => (
          <div key={label} className="space-y-1">
            <label className="text-xs text-muted-foreground">{label}</label>
            <input
              type={type}
              value={value}
              onChange={(e) => setter(e.target.value)}
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
