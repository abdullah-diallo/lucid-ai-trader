import type { Candle, SignalResult } from "../types";
import { atr } from "./utils";

interface OrbRange {
  high: number;
  low: number;
  midpoint: number;
}

export function calculateOrbRange(candles: Candle[]): OrbRange | null {
  if (candles.length < 6) return null;
  // First 3 candles = first 15 minutes on 5m chart
  const orbCandles = candles.slice(0, 3);
  const high = Math.max(...orbCandles.map((c) => c.high));
  const low = Math.min(...orbCandles.map((c) => c.low));
  return { high, low, midpoint: (high + low) / 2 };
}

export function analyzeOrb(candles: Candle[]): SignalResult | null {
  if (candles.length < 5) return null;
  const orb = calculateOrbRange(candles);
  if (!orb) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);
  const orbSize = orb.high - orb.low;

  // Bullish breakout: close above ORB high with momentum
  if (prev.close <= orb.high && current.close > orb.high && current.close > current.open) {
    const breakoutStrength = (current.close - orb.high) / orbSize;
    const confidence = Math.min(0.95, 0.65 + breakoutStrength * 0.3);

    return {
      setupType: "ORB_LONG",
      direction: "BULLISH",
      confidence,
      reason: `ORB bullish breakout above ${orb.high.toFixed(2)}. Range: ${orbSize.toFixed(2)} pts`,
      entryPrice: current.close,
      stopPrice: orb.high - atrVal * 0.5,
      target1: current.close + orbSize * 1.0,
      target2: current.close + orbSize * 2.0,
    };
  }

  // Bearish breakdown: close below ORB low
  if (prev.close >= orb.low && current.close < orb.low && current.close < current.open) {
    const breakoutStrength = (orb.low - current.close) / orbSize;
    const confidence = Math.min(0.95, 0.65 + breakoutStrength * 0.3);

    return {
      setupType: "ORB_SHORT",
      direction: "BEARISH",
      confidence,
      reason: `ORB bearish breakdown below ${orb.low.toFixed(2)}. Range: ${orbSize.toFixed(2)} pts`,
      entryPrice: current.close,
      stopPrice: orb.low + atrVal * 0.5,
      target1: current.close - orbSize * 1.0,
      target2: current.close - orbSize * 2.0,
    };
  }

  return null;
}
