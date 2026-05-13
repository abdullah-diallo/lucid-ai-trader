import { ConvexHttpClient } from "convex/browser";
import { api } from "@/convex/_generated/api";
import { STRATEGY_REGISTRY } from "@/convex/strategies";
import { runStrategy } from "./strategies";
import { routeSignal } from "./state-manager";
import { fetchLiveCandles, isMarketHours, isTimeframeDue } from "./market-data";
import type { TradingSignal, Account, TradingMode } from "./types";

const convex = new ConvexHttpClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

// Default pairs — override with TRADEABLE_PAIRS env var (comma-separated)
const DEFAULT_PAIRS = ["MES1!", "MNQ1!", "ES1!", "NQ1!", "SPY", "QQQ"];

function getEnabledPairs(): string[] {
  const env = process.env.TRADEABLE_PAIRS;
  if (env) return env.split(",").map(p => p.trim()).filter(Boolean);
  return DEFAULT_PAIRS;
}

export interface EngineResult {
  skipped: string | null;
  timeframesRan: string[];
  signalsFound: number;
  signalsRouted: number;
}

export async function runAutonomousEngine(userId: string): Promise<EngineResult> {
  // Load trading state and account in parallel
  const [tradingState, account] = await Promise.all([
    convex.query(api.tradingState.get, { userId }),
    convex.query(api.accounts.getActive, { userId }),
  ]);

  if (!tradingState || tradingState.isPaused) {
    return { skipped: "Trading paused", timeframesRan: [], signalsFound: 0, signalsRouted: 0 };
  }
  if (!account) {
    return { skipped: "No active account", timeframesRan: [], signalsFound: 0, signalsRouted: 0 };
  }

  // Which strategy IDs are enabled for this user
  const enabledIds = await convex.query(api.strategies.getEnabledIds, { userId });
  const enabledSet = new Set(enabledIds);

  // Autonomous strategies only — skip "tv" (TradingView-only) strategies
  const autonomous = STRATEGY_REGISTRY.filter(
    s => enabledSet.has(s.id) && s.timeframe !== "tv"
  );

  // Group by timeframe
  const byTimeframe = new Map<string, string[]>();
  for (const s of autonomous) {
    if (!byTimeframe.has(s.timeframe)) byTimeframe.set(s.timeframe, []);
    byTimeframe.get(s.timeframe)!.push(s.id);
  }

  const pairs = getEnabledPairs();
  const timeframesRan: string[] = [];

  // symbol → best signal found
  type SignalEntry = { strategyId: string; confidence: number; signal: NonNullable<ReturnType<typeof runStrategy>> };
  const best = new Map<string, SignalEntry>();

  for (const [timeframe, strategyIds] of byTimeframe) {
    if (!isTimeframeDue(timeframe)) continue;
    // 5m strategies only run during regular market hours
    if (timeframe === "5m" && !isMarketHours()) continue;

    timeframesRan.push(timeframe);

    for (const symbol of pairs) {
      let candles;
      try {
        candles = await fetchLiveCandles(symbol, timeframe);
      } catch {
        continue;
      }
      if (candles.length < 10) continue;

      for (const id of strategyIds) {
        const signal = runStrategy(id, candles);
        if (!signal || signal.direction === null) continue;

        const existing = best.get(symbol);
        if (!existing || signal.confidence > existing.confidence) {
          best.set(symbol, { strategyId: id, confidence: signal.confidence, signal });
        }
      }
    }
  }

  if (timeframesRan.length === 0) {
    return { skipped: null, timeframesRan: [], signalsFound: 0, signalsRouted: 0 };
  }

  // Sort by confidence, cap at 3 signals per run to prevent overtrading
  const toProcess = Array.from(best.values())
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 3);

  const symbolsByEntry = Array.from(best.entries())
    .sort((a, b) => b[1].confidence - a[1].confidence)
    .slice(0, 3);

  const performance = await convex.query(api.signals.getPerformance, { userId });
  let dailyCount = performance.total;
  let signalsRouted = 0;

  for (const [symbol, entry] of symbolsByEntry) {
    const { signal, strategyId } = entry;

    const tradingSignal: TradingSignal = {
      symbol,
      action: signal.direction === "BULLISH" ? "BUY" : "SELL",
      price: signal.entryPrice,
      timeframe: STRATEGY_REGISTRY.find(s => s.id === strategyId)?.timeframe ?? "AUTO",
      reason: signal.reason,
      strategy: strategyId,
      confidence: signal.confidence,
    };

    const signalId = await convex.mutation(api.signals.add, {
      userId,
      symbol,
      action: tradingSignal.action,
      price: tradingSignal.price,
      timeframe: tradingSignal.timeframe,
      reason: tradingSignal.reason,
      strategy: tradingSignal.strategy,
      confidence: tradingSignal.confidence,
      status: "pending",
    });

    const result = await routeSignal(
      tradingSignal,
      account as unknown as Account,
      tradingState.mode as TradingMode,
      dailyCount,
      signalId
    );

    const finalStatus =
      result.action === "executed"         ? "executed"  :
      result.action === "pending_approval" ? "approved"  :
      result.action === "signal_only"      ? "filtered"  : "filtered";

    await convex.mutation(api.signals.updateStatus, { signalId, status: finalStatus });

    dailyCount++;
    signalsRouted++;
  }

  return {
    skipped: null,
    timeframesRan,
    signalsFound: best.size,
    signalsRouted,
  };
}
