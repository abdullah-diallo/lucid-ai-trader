"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

const AVAILABLE_PAIRS = [
  // Micro Futures
  { symbol: "MES1!", label: "Micro E-mini S&P 500", category: "Futures" },
  { symbol: "MNQ1!", label: "Micro Nasdaq", category: "Futures" },
  { symbol: "M2K1!", label: "Micro Russell 2000", category: "Futures" },
  { symbol: "MYM1!", label: "Micro Dow Jones", category: "Futures" },
  { symbol: "MGC1!", label: "Micro Gold", category: "Futures" },
  { symbol: "MCL1!", label: "Micro Crude Oil", category: "Futures" },
  { symbol: "MBT1!", label: "Micro Bitcoin Futures", category: "Futures" },
  // Standard Futures
  { symbol: "ES1!", label: "E-mini S&P 500", category: "Futures" },
  { symbol: "NQ1!", label: "Nasdaq Futures", category: "Futures" },
  { symbol: "RTY1!", label: "Russell 2000", category: "Futures" },
  { symbol: "YM1!", label: "Dow Jones Futures", category: "Futures" },
  { symbol: "GC1!", label: "Gold Futures", category: "Futures" },
  { symbol: "SI1!", label: "Silver Futures", category: "Futures" },
  { symbol: "CL1!", label: "Crude Oil", category: "Futures" },
  { symbol: "NG1!", label: "Natural Gas", category: "Futures" },
  { symbol: "HG1!", label: "Copper Futures", category: "Futures" },
  { symbol: "ZB1!", label: "30Y Treasury Bond", category: "Futures" },
  { symbol: "ZN1!", label: "10Y Treasury Note", category: "Futures" },
  { symbol: "SPY", label: "S&P 500 ETF", category: "ETF" },
  { symbol: "QQQ", label: "Nasdaq ETF", category: "ETF" },
  { symbol: "IWM", label: "Russell 2000 ETF", category: "ETF" },
  { symbol: "DIA", label: "Dow Jones ETF", category: "ETF" },
  { symbol: "AAPL", label: "Apple", category: "Stocks" },
  { symbol: "TSLA", label: "Tesla", category: "Stocks" },
  { symbol: "NVDA", label: "Nvidia", category: "Stocks" },
  { symbol: "MSFT", label: "Microsoft", category: "Stocks" },
  { symbol: "AMZN", label: "Amazon", category: "Stocks" },
  { symbol: "META", label: "Meta", category: "Stocks" },
  { symbol: "GOOGL", label: "Google", category: "Stocks" },
  // Majors
  { symbol: "EURUSD", label: "Euro / USD", category: "Forex" },
  { symbol: "GBPUSD", label: "GBP / USD", category: "Forex" },
  { symbol: "USDJPY", label: "USD / JPY", category: "Forex" },
  { symbol: "USDCHF", label: "USD / Swiss Franc", category: "Forex" },
  { symbol: "AUDUSD", label: "Australian Dollar / USD", category: "Forex" },
  { symbol: "NZDUSD", label: "New Zealand Dollar / USD", category: "Forex" },
  { symbol: "USDCAD", label: "USD / Canadian Dollar", category: "Forex" },
  // Minors
  { symbol: "EURGBP", label: "Euro / GBP", category: "Forex" },
  { symbol: "EURJPY", label: "Euro / JPY", category: "Forex" },
  { symbol: "GBPJPY", label: "GBP / JPY", category: "Forex" },
  { symbol: "AUDJPY", label: "Australian Dollar / JPY", category: "Forex" },
  { symbol: "EURAUD", label: "Euro / Australian Dollar", category: "Forex" },
  { symbol: "EURCHF", label: "Euro / Swiss Franc", category: "Forex" },
  { symbol: "GBPCHF", label: "GBP / Swiss Franc", category: "Forex" },
  { symbol: "CADJPY", label: "Canadian Dollar / JPY", category: "Forex" },
  { symbol: "NZDJPY", label: "New Zealand Dollar / JPY", category: "Forex" },
  { symbol: "GBPAUD", label: "GBP / Australian Dollar", category: "Forex" },
  { symbol: "GBPCAD", label: "GBP / Canadian Dollar", category: "Forex" },
  { symbol: "AUDCAD", label: "Australian Dollar / Canadian Dollar", category: "Forex" },
  { symbol: "AUDNZD", label: "Australian Dollar / New Zealand Dollar", category: "Forex" },
  // Exotics
  { symbol: "USDZAR", label: "USD / South African Rand", category: "Forex" },
  { symbol: "USDMXN", label: "USD / Mexican Peso", category: "Forex" },
  { symbol: "USDSEK", label: "USD / Swedish Krona", category: "Forex" },
  { symbol: "USDNOK", label: "USD / Norwegian Krone", category: "Forex" },
  { symbol: "USDSGD", label: "USD / Singapore Dollar", category: "Forex" },
  { symbol: "USDTRY", label: "USD / Turkish Lira", category: "Forex" },
  { symbol: "BTCUSD", label: "Bitcoin / USD", category: "Crypto" },
  { symbol: "ETHUSD", label: "Ethereum / USD", category: "Crypto" },
];

const CATEGORIES = ["Futures", "ETF", "Stocks", "Forex", "Crypto"];
const STORAGE_KEY = "lucid_tradeable_pairs";

const DEFAULT_ENABLED = new Set([
  "MES1!", "MNQ1!", "M2K1!", "MYM1!", "ES1!", "NQ1!", "SPY", "QQQ",
]);

function loadEnabled(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch {}
  return new Set(DEFAULT_ENABLED);
}

function saveEnabled(set: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(set)));
  } catch {}
}

export function MarketsView() {
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setEnabled(loadEnabled());
    setLoaded(true);
  }, []);

  function toggle(symbol: string) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      saveEnabled(next);
      return next;
    });
  }

  function enableAll() {
    const all = new Set(AVAILABLE_PAIRS.map((p) => p.symbol));
    setEnabled(all);
    saveEnabled(all);
  }

  function disableAll() {
    setEnabled(new Set());
    saveEnabled(new Set());
  }

  if (!loaded) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Tradeable Pairs</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            The bot will only trade pairs you enable here. {enabled.size} / {AVAILABLE_PAIRS.length} active.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={enableAll} className="text-xs px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
            Enable All
          </button>
          <button onClick={disableAll} className="text-xs px-3 py-1.5 rounded-lg bg-white/5 text-muted-foreground hover:text-foreground transition-colors">
            Disable All
          </button>
        </div>
      </div>

      {CATEGORIES.map((cat) => {
        const catPairs = AVAILABLE_PAIRS.filter((p) => p.category === cat);
        return (
          <div key={cat} className="glass rounded-2xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-muted-foreground">{cat}</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {catPairs.map(({ symbol, label }) => {
                const isEnabled = enabled.has(symbol);
                return (
                  <button
                    key={symbol}
                    onClick={() => toggle(symbol)}
                    className={cn(
                      "flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all",
                      isEnabled
                        ? "bg-primary/10 border-primary/40 text-foreground"
                        : "bg-white/3 border-border text-muted-foreground hover:border-border/60 hover:text-foreground"
                    )}
                  >
                    <div>
                      <p className="text-sm font-medium">{symbol}</p>
                      <p className="text-xs opacity-60">{label}</p>
                    </div>
                    <div className={cn(
                      "w-4 h-4 rounded-full border-2 flex-none transition-colors ml-2",
                      isEnabled ? "bg-primary border-primary" : "border-muted-foreground/40"
                    )} />
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
