import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish } from "./utils";

export function analyzeBos(candles: Candle[]): SignalResult | null {
  if (candles.length < 15) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);

  // Find recent swing high and swing low
  const lookback = candles.slice(-15, -1);
  const swingHigh = Math.max(...lookback.map((c) => c.high));
  const swingLow = Math.min(...lookback.map((c) => c.low));

  // Bullish BOS: close above swing high (structure break)
  if (prev.high <= swingHigh && current.close > swingHigh && isBullish(current)) {
    return {
      setupType: "BOS_BULLISH",
      direction: "BULLISH",
      confidence: 0.72,
      reason: `Break of Structure bullish: close above swing high at ${swingHigh.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: swingHigh - atrVal * 0.5,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Bearish BOS: close below swing low
  if (prev.low >= swingLow && current.close < swingLow && isBearish(current)) {
    return {
      setupType: "BOS_BEARISH",
      direction: "BEARISH",
      confidence: 0.72,
      reason: `Break of Structure bearish: close below swing low at ${swingLow.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: swingLow + atrVal * 0.5,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
