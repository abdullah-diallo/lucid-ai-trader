import type { Candle, SignalResult } from "../types";
import { atr, ema, rsi, isBullish, isBearish } from "./utils";

export function analyzeMomentum(candles: Candle[]): SignalResult | null {
  if (candles.length < 25) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const ema8 = ema(candles, 8);
  const ema21 = ema(candles, 21);
  const rsiVal = rsi(candles);

  const bullishAlignment = ema8[ema8.length - 1] > ema21[ema21.length - 1];
  const bearishAlignment = ema8[ema8.length - 1] < ema21[ema21.length - 1];

  if (bullishAlignment && isBullish(current) && rsiVal > 55 && rsiVal < 80) {
    return {
      setupType: "MOMENTUM_LONG",
      direction: "BULLISH",
      confidence: 0.7,
      reason: `Momentum long: EMA8 > EMA21, RSI ${rsiVal.toFixed(0)}, price above both EMAs`,
      entryPrice: current.close,
      stopPrice: Math.min(ema8[ema8.length - 1], ema21[ema21.length - 1]) - atrVal * 0.3,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  if (bearishAlignment && isBearish(current) && rsiVal < 45 && rsiVal > 20) {
    return {
      setupType: "MOMENTUM_SHORT",
      direction: "BEARISH",
      confidence: 0.7,
      reason: `Momentum short: EMA8 < EMA21, RSI ${rsiVal.toFixed(0)}, price below both EMAs`,
      entryPrice: current.close,
      stopPrice: Math.max(ema8[ema8.length - 1], ema21[ema21.length - 1]) + atrVal * 0.3,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
