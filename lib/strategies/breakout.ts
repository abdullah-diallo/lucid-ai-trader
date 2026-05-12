import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

export function analyzeBreakout(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);

  const resistance = highestHigh(candles.slice(-20, -1), 19);
  const support = lowestLow(candles.slice(-20, -1), 19);

  // Volume confirmation proxy: body > 0.6 * ATR
  const strongBreakout = (current.close - current.open) > atrVal * 0.6;

  if (prev.close <= resistance && current.close > resistance && isBullish(current)) {
    return {
      setupType: "BREAKOUT_LONG",
      direction: "BULLISH",
      confidence: strongBreakout ? 0.78 : 0.68,
      reason: `Breakout long: new high above ${resistance.toFixed(2)}${strongBreakout ? " with momentum" : ""}`,
      entryPrice: current.close,
      stopPrice: resistance - atrVal * 0.75,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  if (prev.close >= support && current.close < support && isBearish(current)) {
    return {
      setupType: "BREAKOUT_SHORT",
      direction: "BEARISH",
      confidence: strongBreakout ? 0.78 : 0.68,
      reason: `Breakout short: new low below ${support.toFixed(2)}${strongBreakout ? " with momentum" : ""}`,
      entryPrice: current.close,
      stopPrice: support + atrVal * 0.75,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
