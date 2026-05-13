"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

const INTERVALS = ["1", "5", "15", "30", "60", "240", "D"];
const SYMBOLS = ["MNQ1!", "MES1!", "MYM1!", "ES1!", "NQ1!", "RTY1!", "YM1!", "SPY", "QQQ"];

declare global {
  interface Window {
    TradingView: {
      widget: new (config: Record<string, unknown>) => unknown;
    };
  }
}

function TradingViewWidget({
  symbol,
  interval,
  theme,
}: {
  symbol: string;
  interval: string;
  theme: "dark" | "light";
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Remove any previously loaded tv.js to force a fresh load
    document.querySelectorAll('script[src*="tv.js"]').forEach((s) => s.remove());

    const containerId = "tv_chart_main";
    containerRef.current.innerHTML = `<div id="${containerId}" style="height:100%;width:100%"></div>`;

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = false;
    script.onload = () => {
      if (!window.TradingView) return;
      new window.TradingView.widget({
        autosize: true,
        symbol,
        interval,
        timezone: "America/New_York",
        theme,
        style: "1",
        locale: "en",
        enable_publishing: false,
        hide_side_toolbar: false,
        allow_symbol_change: true,
        save_image: true,
        withdateranges: true,
        container_id: containerId,
        studies: ["RSI@tv-basicstudies", "VWAP@tv-basicstudies"],
      });
    };

    document.head.appendChild(script);

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  }, [symbol, interval, theme]);

  return <div ref={containerRef} className="h-full w-full" />;
}

export function TradingViewPanel() {
  const [symbol, setSymbol] = useState("MNQ1!");
  const [interval, setInterval] = useState("15");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [widgetKey, setWidgetKey] = useState(0);

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-input border border-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <div className="flex gap-1">
          {INTERVALS.map((i) => (
            <button
              key={i}
              onClick={() => setInterval(i)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                interval === i
                  ? "bg-primary text-white"
                  : "bg-white/5 text-muted-foreground hover:text-foreground"
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
          className="text-xs"
        >
          {theme === "dark" ? "Light" : "Dark"} Theme
        </Button>

        <Button
          variant="outline"
          size="sm"
          className="text-xs ml-auto"
          onClick={() => setWidgetKey((k) => k + 1)}
        >
          Reload Chart
        </Button>
      </div>

      <div className="flex-1 glass rounded-2xl overflow-hidden min-h-0">
        <TradingViewWidget
          key={widgetKey}
          symbol={symbol}
          interval={interval}
          theme={theme}
        />
      </div>
    </div>
  );
}
