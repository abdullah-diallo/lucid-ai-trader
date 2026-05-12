import type { Candle, SignalResult } from "../types";
import { atr, highestHigh, lowestLow, isBullish, isBearish } from "./utils";

type Phase = "accumulation" | "manipulation" | "distribution" | "unknown";

function detectPhase(candles: Candle[]): Phase {
  if (candles.length < 12) return "unknown";
  const third = Math.floor(candles.length / 3);
  const part1 = candles.slice(0, third);
  const part2 = candles.slice(third, third * 2);
  const part3 = candles.slice(third * 2);

  const range1 = highestHigh(part1, part1.length) - lowestLow(part1, part1.length);
  const range2 = highestHigh(part2, part2.length) - lowestLow(part2, part2.length);
  const range3 = highestHigh(part3, part3.length) - lowestLow(part3, part3.length);

  if (range1 < range2 && range3 > range2) return "distribution";
  if (range2 > range1 * 1.5) return "manipulation";
  if (range1 < range2 * 0.7) return "accumulation";
  return "unknown";
}

export function analyzeAmd(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const phase = detectPhase(candles.slice(-20));

  if (phase === "distribution" && isBullish(current)) {
    const low = lowestLow(candles.slice(-20), 20);
    return {
      setupType: "AMD_DISTRIBUTION_LONG",
      direction: "BULLISH",
      confidence: 0.7,
      reason: `AMD distribution phase detected. Price entering distribution zone, bullish bias`,
      entryPrice: current.close,
      stopPrice: low - atrVal * 0.5,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  if (phase === "manipulation" && isBearish(current)) {
    const high = highestHigh(candles.slice(-20), 20);
    return {
      setupType: "AMD_MANIPULATION_SHORT",
      direction: "BEARISH",
      confidence: 0.65,
      reason: `AMD manipulation phase: false breakout trap detected, bearish reversal expected`,
      entryPrice: current.close,
      stopPrice: high + atrVal * 0.5,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 3,
    };
  }

  return null;
}
