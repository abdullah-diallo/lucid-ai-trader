import type { Candle, SignalResult } from "../types";
import { atr, rsi, isBullish, isBearish, bodySize } from "./utils";

export function analyzeFading(candles: Candle[]): SignalResult | null {
  if (candles.length < 15) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);
  const rsiVal = rsi(candles);

  const prevBody = bodySize(prev);
  const isExtended = prevBody > atrVal * 1.5;

  // Fade a large bullish candle (overbought + extended)
  if (isExtended && isBullish(prev) && isBearish(current) && rsiVal > 70) {
    return {
      setupType: "FADING_SHORT",
      direction: "BEARISH",
      confidence: 0.65,
      reason: `Fading extended bull candle (${prevBody.toFixed(0)} pts), RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: prev.high + atrVal * 0.3,
      target1: current.close - atrVal * 1.5,
      target2: current.close - atrVal * 3,
    };
  }

  // Fade a large bearish candle (oversold + extended)
  if (isExtended && isBearish(prev) && isBullish(current) && rsiVal < 30) {
    return {
      setupType: "FADING_LONG",
      direction: "BULLISH",
      confidence: 0.65,
      reason: `Fading extended bear candle (${prevBody.toFixed(0)} pts), RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: prev.low - atrVal * 0.3,
      target1: current.close + atrVal * 1.5,
      target2: current.close + atrVal * 3,
    };
  }

  return null;
}
