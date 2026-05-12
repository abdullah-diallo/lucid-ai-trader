import type { Candle, SignalResult } from "../types";
import { atr, vwap, isBullish, isBearish } from "./utils";

export function analyzeVwap(candles: Candle[]): SignalResult | null {
  if (candles.length < 10) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);
  const vwapVal = vwap(candles);

  const proximity = Math.abs(current.close - vwapVal) / atrVal;
  const crossedAbove = prev.close < vwapVal && current.close > vwapVal;
  const crossedBelow = prev.close > vwapVal && current.close < vwapVal;

  if (crossedAbove && isBullish(current) && proximity < 0.3) {
    return {
      setupType: "VWAP_RECLAIM_LONG",
      direction: "BULLISH",
      confidence: 0.7,
      reason: `VWAP reclaim: price crossed above VWAP at ${vwapVal.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: vwapVal - atrVal * 0.5,
      target1: current.close + atrVal * 1.5,
      target2: current.close + atrVal * 3,
    };
  }

  if (crossedBelow && isBearish(current) && proximity < 0.3) {
    return {
      setupType: "VWAP_REJECTION_SHORT",
      direction: "BEARISH",
      confidence: 0.7,
      reason: `VWAP rejection: price crossed below VWAP at ${vwapVal.toFixed(2)}`,
      entryPrice: current.close,
      stopPrice: vwapVal + atrVal * 0.5,
      target1: current.close - atrVal * 1.5,
      target2: current.close - atrVal * 3,
    };
  }

  return null;
}
