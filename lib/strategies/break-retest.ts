import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

export function analyzeBreakRetest(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);

  // Look for a recent breakout level and a retest
  const lookbackCandles = candles.slice(-20, -5);
  const recentCandles = candles.slice(-5);

  const breakLevel = highestHigh(lookbackCandles, lookbackCandles.length);
  const supportLevel = lowestLow(lookbackCandles, lookbackCandles.length);

  // Bullish: broke above resistance, now retesting it as support
  const retestProximity = atrVal * 0.4;
  const brokeAbove = recentCandles.some((c) => c.high > breakLevel);
  const retesting = Math.abs(current.low - breakLevel) < retestProximity;

  if (brokeAbove && retesting && isBullish(current)) {
    return {
      setupType: "BREAK_RETEST_LONG",
      direction: "BULLISH",
      confidence: 0.75,
      reason: `Break & Retest: breakout above ${breakLevel.toFixed(2)}, now retesting as support`,
      entryPrice: current.close,
      stopPrice: breakLevel - atrVal * 0.75,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Bearish: broke below support, now retesting it as resistance
  const brokBelow = recentCandles.some((c) => c.low < supportLevel);
  const retestingSupport = Math.abs(current.high - supportLevel) < retestProximity;

  if (brokBelow && retestingSupport && isBearish(current)) {
    return {
      setupType: "BREAK_RETEST_SHORT",
      direction: "BEARISH",
      confidence: 0.75,
      reason: `Break & Retest: breakdown below ${supportLevel.toFixed(2)}, now retesting as resistance`,
      entryPrice: current.close,
      stopPrice: supportLevel + atrVal * 0.75,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
