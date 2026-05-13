import type { Candle, SignalResult } from "../types";
import { atr, ema, rsi, sma, isBullish, isBearish } from "./utils";

function winRateScore(candles: Candle[], lookback = 20): number {
  const slice = candles.slice(-lookback);
  const ups = slice.filter((c) => c.close > c.open).length;
  return ups / lookback;
}

export function analyzeProbability(candles: Candle[]): SignalResult | null {
  if (candles.length < 30) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const rsiVal = rsi(candles, 14);

  const ema20 = ema(candles, 20);
  const e20 = ema20[ema20.length - 1];
  const sma50 = sma(candles, Math.min(50, candles.length));

  // Trend alignment score (0-1)
  const trendUp = current.close > e20 && e20 > sma50 ? 1 : 0;
  const trendDown = current.close < e20 && e20 < sma50 ? 1 : 0;

  // RSI probability score
  const rsiScoreLong = rsiVal > 45 && rsiVal < 65 ? 0.2 : rsiVal > 30 && rsiVal <= 45 ? 0.1 : 0;
  const rsiScoreShort = rsiVal < 55 && rsiVal > 35 ? 0.2 : rsiVal < 70 && rsiVal >= 55 ? 0.1 : 0;

  // Recent win rate as a probability component
  const wrScore = winRateScore(candles);

  // Volatility regime: moderate ATR relative to price = better probability
  const atrRatio = atrVal / current.close;
  const volScore = atrRatio > 0.003 && atrRatio < 0.025 ? 0.15 : 0;

  const probLong = trendUp * 0.4 + rsiScoreLong + wrScore * 0.15 + volScore;
  const probShort = trendDown * 0.4 + rsiScoreShort + (1 - wrScore) * 0.15 + volScore;

  if (probLong >= 0.65 && isBullish(current)) {
    return {
      setupType: "PROBABILITY_LONG",
      direction: "BULLISH",
      confidence: Math.min(0.88, probLong),
      reason: `Probability engine: ${(probLong * 100).toFixed(0)}% long score — trend, RSI, win rate aligned`,
      entryPrice: current.close,
      stopPrice: current.close - atrVal * 1.5,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 3.5,
    };
  }

  if (probShort >= 0.65 && isBearish(current)) {
    return {
      setupType: "PROBABILITY_SHORT",
      direction: "BEARISH",
      confidence: Math.min(0.88, probShort),
      reason: `Probability engine: ${(probShort * 100).toFixed(0)}% short score — trend, RSI, win rate aligned`,
      entryPrice: current.close,
      stopPrice: current.close + atrVal * 1.5,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 3.5,
    };
  }

  return null;
}
