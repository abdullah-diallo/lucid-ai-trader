import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish, highestHigh, lowestLow } from "./utils";

// Killzone windows (ET hours): London (3-5), NY Open (9:30-11), NY PM (14-16)
function isKillzone(hour: number, minute: number): string | null {
  const t = hour * 60 + minute;
  if (t >= 3 * 60 && t < 5 * 60) return "London";
  if (t >= 9 * 60 + 30 && t < 11 * 60) return "NY_Open";
  if (t >= 14 * 60 && t < 16 * 60) return "NY_PM";
  return null;
}

function detectFairValueGap(candles: Candle[]): { level: number; direction: "BULLISH" | "BEARISH" } | null {
  if (candles.length < 3) return null;
  const [a, , c] = candles.slice(-3);
  if (c.low > a.high) return { level: (c.low + a.high) / 2, direction: "BULLISH" };
  if (c.high < a.low) return { level: (c.high + a.low) / 2, direction: "BEARISH" };
  return null;
}

export function analyzeIctSmc(candles: Candle[]): SignalResult | null {
  if (candles.length < 20) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const now = new Date();
  const killzone = isKillzone(now.getHours(), now.getMinutes());
  const fvg = detectFairValueGap(candles);

  const swingHigh = highestHigh(candles.slice(-20), 20);
  const swingLow = lowestLow(candles.slice(-20), 20);

  // Full ICT model: killzone + FVG + structure
  if (killzone && fvg) {
    if (fvg.direction === "BULLISH" && isBullish(current)) {
      return {
        setupType: "ICT_BULLISH_FVG",
        direction: "BULLISH",
        confidence: 0.82,
        reason: `ICT model: bullish FVG at ${fvg.level.toFixed(2)} during ${killzone} killzone`,
        entryPrice: current.close,
        stopPrice: fvg.level - atrVal,
        target1: swingHigh,
        target2: swingHigh + atrVal * 2,
      };
    }

    if (fvg.direction === "BEARISH" && isBearish(current)) {
      return {
        setupType: "ICT_BEARISH_FVG",
        direction: "BEARISH",
        confidence: 0.82,
        reason: `ICT model: bearish FVG at ${fvg.level.toFixed(2)} during ${killzone} killzone`,
        entryPrice: current.close,
        stopPrice: fvg.level + atrVal,
        target1: swingLow,
        target2: swingLow - atrVal * 2,
      };
    }
  }

  return null;
}
