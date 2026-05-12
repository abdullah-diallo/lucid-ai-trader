import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish } from "./utils";

export function analyzeAsiaRange(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  // Use first 8 candles as Asia session range (assuming 1h chart starting at 20:00 ET)
  const asiaCandles = candles.slice(0, 8);
  const asiaHigh = Math.max(...asiaCandles.map((c) => c.high));
  const asiaLow = Math.min(...asiaCandles.map((c) => c.low));
  const atrVal = atr(candles);

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];

  // Bullish breakout above Asia range into RTH
  if (prev.close <= asiaHigh && current.close > asiaHigh && isBullish(current)) {
    return {
      setupType: "ASIA_RANGE_BREAKOUT_LONG",
      direction: "BULLISH",
      confidence: 0.72,
      reason: `Asia range breakout long above ${asiaHigh.toFixed(2)} (range: ${(asiaHigh - asiaLow).toFixed(2)} pts)`,
      entryPrice: current.close,
      stopPrice: asiaHigh - atrVal * 0.5,
      target1: current.close + (asiaHigh - asiaLow),
      target2: current.close + (asiaHigh - asiaLow) * 2,
    };
  }

  // Bearish breakdown below Asia range
  if (prev.close >= asiaLow && current.close < asiaLow && isBearish(current)) {
    return {
      setupType: "ASIA_RANGE_BREAKOUT_SHORT",
      direction: "BEARISH",
      confidence: 0.72,
      reason: `Asia range breakout short below ${asiaLow.toFixed(2)} (range: ${(asiaHigh - asiaLow).toFixed(2)} pts)`,
      entryPrice: current.close,
      stopPrice: asiaLow + atrVal * 0.5,
      target1: current.close - (asiaHigh - asiaLow),
      target2: current.close - (asiaHigh - asiaLow) * 2,
    };
  }

  return null;
}
