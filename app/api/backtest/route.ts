import { NextRequest, NextResponse } from "next/server";
import { runStrategy } from "@/lib/strategies";
import type { Candle, BacktestResult } from "@/lib/types";

const YF_SYMBOL_MAP: Record<string, string> = {
  "MES1!": "ES=F",
  "MNQ1!": "NQ=F",
  "M2K1!": "RTY=F",
  "MYM1!": "YM=F",
  "MGC1!": "GC=F",
  "MCL1!": "CL=F",
  "MBT1!": "BTC=F",
  "ES1!": "ES=F",
  "NQ1!": "NQ=F",
  "RTY1!": "RTY=F",
  "YM1!": "YM=F",
  "GC1!": "GC=F",
  "SI1!": "SI=F",
  "CL1!": "CL=F",
  "NG1!": "NG=F",
  "HG1!": "HG=F",
  "ZB1!": "ZB=F",
  "ZN1!": "ZN=F",
  "EURUSD": "EURUSD=X",
  "GBPUSD": "GBPUSD=X",
  "USDJPY": "JPY=X",
};

const YF_INTERVAL_MAP: Record<string, string> = {
  "1d": "1d",
  "1h": "60m",
  "15m": "15m",
};

async function fetchOhlcv(symbol: string, start: string, end: string, timeframe = "1d"): Promise<Candle[]> {
  const yfSymbol = YF_SYMBOL_MAP[symbol] ?? symbol;
  const interval = YF_INTERVAL_MAP[timeframe] ?? "1d";

  // Yahoo Finance caps intraday ranges: 60m = 730 days, 15m = 60 days
  let startDate = new Date(start);
  const endDate = new Date(end);
  if (timeframe === "15m") {
    const cap = new Date(endDate);
    cap.setDate(cap.getDate() - 58);
    if (startDate < cap) startDate = cap;
  } else if (timeframe === "1h") {
    const cap = new Date(endDate);
    cap.setFullYear(cap.getFullYear() - 2);
    if (startDate < cap) startDate = cap;
  }

  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);

  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yfSymbol)}?period1=${period1}&period2=${period2}&interval=${interval}&events=history`;

  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json",
      "Accept-Language": "en-US,en;q=0.9",
    },
  });

  if (!res.ok) throw new Error(`Yahoo Finance returned HTTP ${res.status} for ${yfSymbol}`);

  const json = await res.json();
  const result = json?.chart?.result?.[0];
  if (!result) throw new Error(`No data returned for ${yfSymbol}`);

  const timestamps: number[] = result.timestamp ?? [];
  const quotes = result.indicators?.quote?.[0] ?? {};
  const opens: number[] = quotes.open ?? [];
  const highs: number[] = quotes.high ?? [];
  const lows: number[] = quotes.low ?? [];
  const closes: number[] = quotes.close ?? [];
  const volumes: number[] = quotes.volume ?? [];

  return timestamps
    .map((t, i) => ({
      time: t,
      open: opens[i] ?? 0,
      high: highs[i] ?? 0,
      low: lows[i] ?? 0,
      close: closes[i] ?? 0,
      volume: volumes[i] ?? 0,
    }))
    .filter((c) => c.close != null && c.close !== 0);
}

export async function POST(req: NextRequest) {
  const { strategyId, symbol, start, end, startingBalance, qty, timeframe = "1d" } = await req.json() as {
    strategyId: string;
    symbol: string;
    start: string;
    end: string;
    startingBalance: number;
    qty: number;
    timeframe?: string;
  };

  let candles: Candle[] = [];
  try {
    candles = await fetchOhlcv(symbol, start, end, timeframe);
  } catch (err) {
    return NextResponse.json({ error: `Failed to fetch data: ${String(err)}` }, { status: 400 });
  }

  const minBars = timeframe === "1d" ? 30 : 50;
  if (candles.length < minBars) {
    return NextResponse.json(
      { error: `Only ${candles.length} bars returned for ${symbol}. Try a wider date range or a different symbol like SPY.` },
      { status: 400 }
    );
  }

  const trades: BacktestResult["trades"] = [];
  const equityCurve = [startingBalance];
  let equity = startingBalance;
  let openTrade: { entryPrice: number; side: "Long" | "Short"; entryBar: number } | null = null;

  for (let i = 30; i < candles.length; i++) {
    const current = candles[i];

    // Close open trade after holding 5 bars
    if (openTrade && i - openTrade.entryBar >= 5) {
      const pnl =
        openTrade.side === "Long"
          ? (current.close - openTrade.entryPrice) * qty
          : (openTrade.entryPrice - current.close) * qty;

      trades.push({
        entryPrice: openTrade.entryPrice,
        exitPrice: current.close,
        side: openTrade.side,
        qty,
        pnl,
        entryBar: openTrade.entryBar,
        exitBar: i,
        strategy: strategyId,
      });

      equity += pnl;
      equityCurve.push(equity);
      openTrade = null;
    }

    // Enter new trade if no position open
    if (!openTrade) {
      const slice = candles.slice(0, i + 1);
      const signal = runStrategy(strategyId, slice);
      if (signal) {
        openTrade = {
          entryPrice: signal.entryPrice,
          side: signal.direction === "BULLISH" ? "Long" : "Short",
          entryBar: i,
        };
      }
    }
  }

  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);
  const grossProfit = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));

  const result: BacktestResult = {
    strategy: strategyId,
    symbol,
    start,
    end,
    trades,
    equityCurve,
    metrics: {
      totalTrades: trades.length,
      wins: wins.length,
      losses: losses.length,
      winRate: trades.length > 0 ? wins.length / trades.length : 0,
      grossProfit,
      grossLoss,
      netPnl: grossProfit - grossLoss,
      avgWin: wins.length > 0 ? grossProfit / wins.length : 0,
      avgLoss: losses.length > 0 ? grossLoss / losses.length : 0,
      profitFactor: grossLoss > 0 ? grossProfit / grossLoss : 0,
      sharpe: 0,
      sortino: 0,
      maxDrawdown: 0,
      consecutiveWins: 0,
      consecutiveLosses: 0,
    },
  };

  return NextResponse.json(result);
}
