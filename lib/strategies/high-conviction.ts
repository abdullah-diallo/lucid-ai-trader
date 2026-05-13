import type { Candle, SignalResult } from "../types";
import { atr, ema, rsi, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

export function analyzeHighConviction(candles: Candle[]): SignalResult | null {
  if (candles.length < 50) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const rsiVal = rsi(candles, 14);

  const ema20 = ema(candles, 20);
  const ema50 = ema(candles, 50);
  const e20 = ema20[ema20.length - 1];
  const e50 = ema50[ema50.length - 1];

  const high20 = highestHigh(candles, 20);
  const low20 = lowestLow(candles, 20);

  // Volume surge: current volume > 1.5x average
  const avgVol = candles.slice(-20).reduce((s, c) => s + c.volume, 0) / 20;
  const volSurge = current.volume > avgVol * 1.5;

  // Score bullish conditions
  const bullishScore = [
    e20 > e50,                          // uptrend structure
    current.close > e20,                // price above EMA
    rsiVal > 50 && rsiVal < 70,         // momentum zone (not overbought)
    isBullish(current),                 // bullish candle
    current.close > high20 * 0.995,     // near or at 20-bar high
    volSurge,                           // confirmed by volume
  ].filter(Boolean).length;

  // Score bearish conditions
  const bearishScore = [
    e20 < e50,
    current.close < e20,
    rsiVal < 50 && rsiVal > 30,
    isBearish(current),
    current.close < low20 * 1.005,
    volSurge,
  ].filter(Boolean).length;

  if (bullishScore >= 4 && isBullish(current)) {
    return {
      setupType: "HIGH_CONVICTION_LONG",
      direction: "BULLISH",
      confidence: Math.min(0.92, 0.65 + bullishScore * 0.05),
      reason: `High conviction long: ${bullishScore}/6 conditions met — EMA trend, RSI, volume, structure aligned`,
      entryPrice: current.close,
      stopPrice: current.low - atrVal,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  if (bearishScore >= 4 && isBearish(current)) {
    return {
      setupType: "HIGH_CONVICTION_SHORT",
      direction: "BEARISH",
      confidence: Math.min(0.92, 0.65 + bearishScore * 0.05),
      reason: `High conviction short: ${bearishScore}/6 conditions met — EMA trend, RSI, volume, structure aligned`,
      entryPrice: current.close,
      stopPrice: current.high + atrVal,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
