import type { Candle, SignalResult } from "../types";
import { atr, ema, rsi, isBullish, isBearish } from "./utils";

export function analyzeScalping(candles: Candle[]): SignalResult | null {
  if (candles.length < 15) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);
  const ema5 = ema(candles, 5);
  const ema13 = ema(candles, 13);
  const rsiVal = rsi(candles, 9);

  const crossedAbove =
    ema5[ema5.length - 2] < ema13[ema13.length - 2] &&
    ema5[ema5.length - 1] > ema13[ema13.length - 1];

  const crossedBelow =
    ema5[ema5.length - 2] > ema13[ema13.length - 2] &&
    ema5[ema5.length - 1] < ema13[ema13.length - 1];

  if (crossedAbove && rsiVal > 50 && isBullish(current)) {
    return {
      setupType: "SCALP_LONG",
      direction: "BULLISH",
      confidence: 0.65,
      reason: `Scalp long: EMA5 crossed above EMA13, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.close - atrVal * 0.5,
      target1: current.close + atrVal * 0.75,
      target2: current.close + atrVal * 1.5,
    };
  }

  if (crossedBelow && rsiVal < 50 && isBearish(current)) {
    return {
      setupType: "SCALP_SHORT",
      direction: "BEARISH",
      confidence: 0.65,
      reason: `Scalp short: EMA5 crossed below EMA13, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.close + atrVal * 0.5,
      target1: current.close - atrVal * 0.75,
      target2: current.close - atrVal * 1.5,
    };
  }

  return null;
}
