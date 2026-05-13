import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish, bodySize } from "./utils";

export function analyzeNewsSentiment(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);

  // Volume-based news detection: volume > 2x 20-period average = likely news/event day
  const avgVol = candles.slice(-21, -1).reduce((s, c) => s + c.volume, 0) / 20;
  const isNewsDay = current.volume > avgVol * 2;

  if (!isNewsDay) return null;

  const body = bodySize(current);
  const isStrongMove = body > atrVal * 1.2;

  if (!isStrongMove) return null;

  // Trade follow-through on strong news candles (momentum, not fade)
  if (isBullish(current) && current.close > prev.high) {
    return {
      setupType: "NEWS_SENTIMENT_LONG",
      direction: "BULLISH",
      confidence: 0.72,
      reason: `News sentiment: ${(current.volume / avgVol).toFixed(1)}x avg volume with ${body.toFixed(1)}pt bullish breakout candle`,
      entryPrice: current.close,
      stopPrice: current.low - atrVal * 0.5,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 3.5,
    };
  }

  if (isBearish(current) && current.close < prev.low) {
    return {
      setupType: "NEWS_SENTIMENT_SHORT",
      direction: "BEARISH",
      confidence: 0.72,
      reason: `News sentiment: ${(current.volume / avgVol).toFixed(1)}x avg volume with ${body.toFixed(1)}pt bearish breakdown candle`,
      entryPrice: current.close,
      stopPrice: current.high + atrVal * 0.5,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 3.5,
    };
  }

  return null;
}
