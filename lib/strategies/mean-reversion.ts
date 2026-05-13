import type { Candle, SignalResult } from "../types";
import { atr, ema, sma, isBullish, isBearish, rsi } from "./utils";

export function analyzeMeanReversion(candles: Candle[]): SignalResult | null {
  if (candles.length < 25) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const ema20 = ema(candles, 20);
  const mean = ema20[ema20.length - 1];
  const rsiVal = rsi(candles, 14);
  const deviation = (current.close - mean) / atrVal;

  // Oversold: price far below mean, RSI oversold
  if (deviation < -1.5 && rsiVal < 40 && isBullish(current)) {
    return {
      setupType: "MEAN_REVERSION_LONG",
      direction: "BULLISH",
      confidence: Math.min(0.85, 0.65 + Math.abs(deviation + 2.5) * 0.05),
      reason: `Mean reversion long: price ${Math.abs(deviation).toFixed(1)}x ATR below EMA20, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.low - atrVal * 0.5,
      target1: mean,
      target2: mean + atrVal,
    };
  }

  // Overbought: price far above mean, RSI overbought
  if (deviation > 1.5 && rsiVal > 60 && isBearish(current)) {
    return {
      setupType: "MEAN_REVERSION_SHORT",
      direction: "BEARISH",
      confidence: Math.min(0.85, 0.65 + (deviation - 2.5) * 0.05),
      reason: `Mean reversion short: price ${deviation.toFixed(1)}x ATR above EMA20, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.high + atrVal * 0.5,
      target1: mean,
      target2: mean - atrVal,
    };
  }

  return null;
}
