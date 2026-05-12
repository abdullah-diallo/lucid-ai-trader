import type { Candle, SignalResult } from "../types";
import { atr, ema, rsi, isBullish, isBearish } from "./utils";

export function analyzeTrendFollowing(candles: Candle[]): SignalResult | null {
  if (candles.length < 50) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const ema20 = ema(candles, 20);
  const ema50 = ema(candles, 50);
  const rsiVal = rsi(candles);

  const bullTrend = ema20[ema20.length - 1] > ema50[ema50.length - 1];
  const bearTrend = ema20[ema20.length - 1] < ema50[ema50.length - 1];

  // Pullback in uptrend — buy the dip toward EMA20
  if (bullTrend && current.close > ema20[ema20.length - 1] && rsiVal > 45 && rsiVal < 65 && isBullish(current)) {
    return {
      setupType: "TREND_PULLBACK_LONG",
      direction: "BULLISH",
      confidence: 0.73,
      reason: `Trend pullback long: price above EMA20 in uptrend, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: ema20[ema20.length - 1] - atrVal * 0.5,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Pullback in downtrend — sell the rally toward EMA20
  if (bearTrend && current.close < ema20[ema20.length - 1] && rsiVal > 35 && rsiVal < 55 && isBearish(current)) {
    return {
      setupType: "TREND_PULLBACK_SHORT",
      direction: "BEARISH",
      confidence: 0.73,
      reason: `Trend pullback short: price below EMA20 in downtrend, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: ema20[ema20.length - 1] + atrVal * 0.5,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
