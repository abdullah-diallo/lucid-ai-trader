import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

export function analyzeLiquiditySweep(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);

  const prevHigh = highestHigh(candles.slice(-20, -1), 19);
  const prevLow = lowestLow(candles.slice(-20, -1), 19);

  // Bullish: swept lows then reversed
  const sweptLows = prev.low < prevLow;
  const reversed = current.close > prev.close && isBullish(current);

  if (sweptLows && reversed) {
    return {
      setupType: "LIQUIDITY_SWEEP_LONG",
      direction: "BULLISH",
      confidence: 0.78,
      reason: `Liquidity sweep: stop hunt below ${prevLow.toFixed(2)}, reversal confirmed`,
      entryPrice: current.close,
      stopPrice: prev.low - atrVal * 0.3,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Bearish: swept highs then reversed
  const sweptHighs = prev.high > prevHigh;
  const reversedDown = current.close < prev.close && isBearish(current);

  if (sweptHighs && reversedDown) {
    return {
      setupType: "LIQUIDITY_SWEEP_SHORT",
      direction: "BEARISH",
      confidence: 0.78,
      reason: `Liquidity sweep: stop hunt above ${prevHigh.toFixed(2)}, reversal confirmed`,
      entryPrice: current.close,
      stopPrice: prev.high + atrVal * 0.3,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
