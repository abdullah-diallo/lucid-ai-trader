import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish } from "./utils";

export function analyzeGapAndGo(candles: Candle[]): SignalResult | null {
  if (candles.length < 5) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);

  const gapUp = current.open > prev.high;
  const gapDown = current.open < prev.low;
  const gapSize = gapUp ? current.open - prev.high : gapDown ? prev.low - current.open : 0;

  if (gapSize < atrVal * 0.5) return null; // gap too small

  // Gap up + first candle bullish = go long
  if (gapUp && isBullish(current)) {
    return {
      setupType: "GAP_AND_GO_LONG",
      direction: "BULLISH",
      confidence: Math.min(0.8, 0.65 + (gapSize / atrVal) * 0.05),
      reason: `Gap & Go long: gap up ${gapSize.toFixed(2)} pts above ${prev.high.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: current.open - atrVal * 0.5,
      target1: current.close + gapSize,
      target2: current.close + gapSize * 2,
    };
  }

  // Gap down + first candle bearish = go short
  if (gapDown && isBearish(current)) {
    return {
      setupType: "GAP_AND_GO_SHORT",
      direction: "BEARISH",
      confidence: Math.min(0.8, 0.65 + (gapSize / atrVal) * 0.05),
      reason: `Gap & Go short: gap down ${gapSize.toFixed(2)} pts below ${prev.low.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: current.open + atrVal * 0.5,
      target1: current.close - gapSize,
      target2: current.close - gapSize * 2,
    };
  }

  return null;
}
