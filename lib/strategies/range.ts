import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish, rsi } from "./utils";

export function analyzeRange(candles: Candle[]): SignalResult | null {
  if (candles.length < 30) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const rangeHigh = highestHigh(candles, 30);
  const rangeLow = lowestLow(candles, 30);
  const rangeSize = rangeHigh - rangeLow;
  const rsiVal = rsi(candles);

  if (rangeSize < atrVal * 3) return null; // too narrow

  const proximity = atrVal * 0.5;

  // Near support: buy the range low
  if (Math.abs(current.close - rangeLow) < proximity && rsiVal < 45 && isBullish(current)) {
    return {
      setupType: "RANGE_SUPPORT_LONG",
      direction: "BULLISH",
      confidence: 0.68,
      reason: `Range support bounce at ${rangeLow.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: rangeLow - atrVal * 0.5,
      target1: (rangeHigh + rangeLow) / 2,
      target2: rangeHigh,
    };
  }

  // Near resistance: sell the range high
  if (Math.abs(current.close - rangeHigh) < proximity && rsiVal > 55 && isBearish(current)) {
    return {
      setupType: "RANGE_RESISTANCE_SHORT",
      direction: "BEARISH",
      confidence: 0.68,
      reason: `Range resistance rejection at ${rangeHigh.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: rangeHigh + atrVal * 0.5,
      target1: (rangeHigh + rangeLow) / 2,
      target2: rangeLow,
    };
  }

  return null;
}
