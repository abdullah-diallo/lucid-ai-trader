import type { Candle, SignalResult } from "../types";
import { analyzeOrb } from "./orb";
import { analyzeVwap } from "./vwap";
import { analyzeFibonacci } from "./fibonacci";
import { analyzeMeanReversion } from "./mean-reversion";
import { analyzeBos } from "./bos";

// Runs multiple strategies and returns a signal only when 2+ agree on direction
export function analyzeConfluence(candles: Candle[]): SignalResult | null {
  const results = [
    analyzeOrb(candles),
    analyzeVwap(candles),
    analyzeFibonacci(candles),
    analyzeMeanReversion(candles),
    analyzeBos(candles),
  ].filter(Boolean) as SignalResult[];

  if (results.length < 2) return null;

  const bullish = results.filter((r) => r.direction === "BULLISH");
  const bearish = results.filter((r) => r.direction === "BEARISH");

  if (bullish.length >= 2) {
    const avgConfidence = bullish.reduce((s, r) => s + r.confidence, 0) / bullish.length;
    const best = bullish.reduce((a, b) => (a.confidence > b.confidence ? a : b));
    return {
      ...best,
      setupType: "CONFLUENCE_BULLISH",
      confidence: Math.min(0.95, avgConfidence + 0.1 * (bullish.length - 1)),
      reason: `Confluence (${bullish.length} signals agree): ${bullish.map((r) => r.setupType).join(", ")}`,
    };
  }

  if (bearish.length >= 2) {
    const avgConfidence = bearish.reduce((s, r) => s + r.confidence, 0) / bearish.length;
    const best = bearish.reduce((a, b) => (a.confidence > b.confidence ? a : b));
    return {
      ...best,
      setupType: "CONFLUENCE_BEARISH",
      confidence: Math.min(0.95, avgConfidence + 0.1 * (bearish.length - 1)),
      reason: `Confluence (${bearish.length} signals agree): ${bearish.map((r) => r.setupType).join(", ")}`,
    };
  }

  return null;
}
