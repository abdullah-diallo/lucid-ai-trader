"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

const INTERVALS = ["1", "5", "15", "30", "60", "240", "D"];
const SYMBOLS = ["MES1!", "MNQ1!", "ES1!", "NQ1!", "RTY1!", "YM1!", "SPY", "QQQ"];

declare global {
  interface Window {
    TradingView: {
      widget: new (config: Record<string, unknown>) => unknown;
    };
  }
}

export function TradingViewPanel() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [symbol, setSymbol] = useState("MES1!");
  const [interval, setInterval] = useState("15");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "America/New_York",
      theme,
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      studies: ["RSI@tv-basicstudies", "VWAP@tv-basicstudies"],
      container_id: "tv_chart_container",
    });

    if (containerRef.current) {
      containerRef.current.innerHTML = "";
      const wrapper = document.createElement("div");
      wrapper.className = "tradingview-widget-container__widget h-full";
      containerRef.current.appendChild(wrapper);
      containerRef.current.appendChild(script);
    }

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  }, [symbol, interval, theme]);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Controls */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-input border border-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <div className="flex gap-1">
          {INTERVALS.map((i) => (
            <button
              key={i}
              onClick={() => setInterval(i)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                interval === i ? "bg-primary text-white" : "bg-white/5 text-muted-foreground hover:text-foreground"
              }`}
            >
              {i === "D" ? "1D" : `${i}m`}
            </button>
          ))}
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="text-xs ml-auto"
        >
          {theme === "dark" ? "Light" : "Dark"} Theme
        </Button>
      </div>

      {/* Chart */}
      <div className="flex-1 glass rounded-2xl overflow-hidden min-h-0">
        <div id="tv_chart_container" ref={containerRef} className="tradingview-widget-container h-full w-full" />
      </div>
    </div>
  );
}
