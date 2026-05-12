import { NextRequest, NextResponse } from "next/server";
import { runStrategy } from "@/lib/strategies";
import type { Candle, BacktestResult } from "@/lib/types";

async function fetchOhlcv(symbol: string, start: string, end: string): Promise<Candle[]> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const yf = (await import("yahoo-finance2")) as any;
    const client = yf.default ?? yf;
    const data = await client.chart(symbol, {
      period1: start,
      period2: end,
      interval: "1d",
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const quotes: any[] = data?.quotes ?? data?.indicators?.quote?.[0] ?? [];
    return quotes
      .filter((bar: { close: number | null }) => bar.close !== null)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .map((bar: any) => ({
        time: new Date(bar.date ?? bar.timestamp * 1000).getTime() / 1000,
        open: bar.open ?? 0,
        high: bar.high ?? 0,
        low: bar.low ?? 0,
        close: bar.close ?? 0,
        volume: bar.volume ?? 0,
      }));
  } catch {
    return [];
  }
}

export async function POST(req: NextRequest) {
  const { strategyId, symbol, start, end, startingBalance, qty } = await req.json() as {
    strategyId: string;
    symbol: string;
    start: string;
    end: string;
    startingBalance: number;
    qty: number;
  };

  const candles = await fetchOhlcv(symbol, start, end);
  if (candles.length < 30) {
    return NextResponse.json({ error: "Insufficient data" }, { status: 400 });
  }

  const trades: BacktestResult["trades"] = [];
  const equityCurve = [startingBalance];
  let equity = startingBalance;
  let openTrade: { entryPrice: number; side: "Long" | "Short"; entryBar: number } | null = null;

  for (let i = 30; i < candles.length; i++) {
    const slice = candles.slice(0, i + 1);
    const signal = runStrategy(strategyId, slice);

    if (!openTrade && signal) {
      openTrade = {
        entryPrice: signal.entryPrice,
        side: signal.direction === "BULLISH" ? "Long" : "Short",
        entryBar: i,
      };
    } else if (openTrade) {
      const current = candles[i];
      // Simple exit: hold for 5 bars or stop hit
      const held = i - openTrade.entryBar;
      if (held >= 5) {
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
