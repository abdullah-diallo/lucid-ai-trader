import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish, bodySize } from "./utils";
import { isNewsWindow } from "../session-manager";

export function analyzeNewsSpike(candles: Candle[]): SignalResult | null {
  if (candles.length < 5) return null;

  if (!isNewsWindow()) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const body = bodySize(current);

  // News spike: current candle has body > 2x ATR
  const isSpike = body > atrVal * 2;
  if (!isSpike) return null;

  // Fade the spike
  if (isBullish(current)) {
    return {
      setupType: "NEWS_SPIKE_FADE_SHORT",
      direction: "BEARISH",
      confidence: 0.68,
      reason: `News spike fade: bullish spike of ${body.toFixed(1)} pts during news window`,
      entryPrice: current.close,
      stopPrice: current.high + atrVal * 0.5,
      target1: current.open,
      target2: current.open - atrVal,
    };
  }

  if (isBearish(current)) {
    return {
      setupType: "NEWS_SPIKE_FADE_LONG",
      direction: "BULLISH",
      confidence: 0.68,
      reason: `News spike fade: bearish spike of ${body.toFixed(1)} pts during news window`,
      entryPrice: current.close,
      stopPrice: current.low - atrVal * 0.5,
      target1: current.open,
      target2: current.open + atrVal,
    };
  }

  return null;
}
