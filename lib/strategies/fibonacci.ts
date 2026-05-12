import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

const FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786];

export function analyzeFibonacci(candles: Candle[]): SignalResult | null {
  if (candles.length < 30) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const swingHigh = highestHigh(candles, 20);
  const swingLow = lowestLow(candles, 20);
  const range = swingHigh - swingLow;

  if (range < atrVal * 2) return null; // range too small

  // Check if price is at a fib level
  for (const level of [0.618, 0.786]) {
    // Bullish: retracing from high down to fib level
    const fibBull = swingHigh - range * level;
    const fibBear = swingLow + range * level;

    const proximity = atrVal * 0.3;

    if (Math.abs(current.close - fibBull) < proximity && isBullish(current)) {
      return {
        setupType: "FIB_RETRACEMENT_LONG",
        direction: "BULLISH",
        confidence: level === 0.786 ? 0.75 : 0.7,
        reason: `Fibonacci ${(level * 100).toFixed(0)}% retracement at ${fibBull.toFixed(2)}`,
        entryPrice: current.close,
        stopPrice: fibBull - atrVal,
        target1: swingHigh,
        target2: swingHigh + range * 0.382,
      };
    }

    if (Math.abs(current.close - fibBear) < proximity && isBearish(current)) {
      return {
        setupType: "FIB_RETRACEMENT_SHORT",
        direction: "BEARISH",
        confidence: level === 0.786 ? 0.75 : 0.7,
        reason: `Fibonacci ${(level * 100).toFixed(0)}% retracement at ${fibBear.toFixed(2)}`,
        entryPrice: current.close,
        stopPrice: fibBear + atrVal,
        target1: swingLow,
        target2: swingLow - range * 0.382,
      };
    }
  }

  return null;
}
