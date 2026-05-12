import type { Candle, SignalResult } from "../types";
import { atr, isBullish, isBearish, bodySize } from "./utils";

interface OrderBlock {
  level: number;
  direction: "BULLISH" | "BEARISH";
  strength: number;
}

function findOrderBlocks(candles: Candle[], lookback = 20): OrderBlock[] {
  const blocks: OrderBlock[] = [];
  const slice = candles.slice(-lookback);

  for (let i = 2; i < slice.length - 2; i++) {
    const c = slice[i];
    const next = slice[i + 1];
    const prev = slice[i - 1];

    // Bullish OB: bearish candle followed by strong bullish move
    if (isBearish(c) && isBullish(next) && next.close > c.high) {
      blocks.push({ level: c.low, direction: "BULLISH", strength: bodySize(next) / bodySize(c) });
    }

    // Bearish OB: bullish candle followed by strong bearish move
    if (isBullish(c) && isBearish(next) && next.close < c.low) {
      blocks.push({ level: c.high, direction: "BEARISH", strength: bodySize(next) / bodySize(c) });
    }
  }
  return blocks;
}

function hasFairValueGap(candles: Candle[], i: number): boolean {
  if (i < 2) return false;
  const prev = candles[i - 2];
  const curr = candles[i];
  // Bullish FVG: gap between prev.high and curr.low
  return curr.low > prev.high || prev.low > curr.high;
}

export function analyzeSmc(candles: Candle[]): SignalResult | null {
  if (candles.length < 25) return null;

  const current = candles[candles.length - 1];
  const atrVal = atr(candles);
  const blocks = findOrderBlocks(candles);

  for (const block of blocks) {
    const proximity = Math.abs(current.close - block.level) / atrVal;

    if (proximity <= 0.5) {
      if (block.direction === "BULLISH" && current.close > block.level && isBullish(current)) {
        const confidence = Math.min(0.9, 0.65 + (1 - proximity) * 0.2 + Math.min(block.strength - 1, 0.5) * 0.1);
        return {
          setupType: "SMC_BULLISH_OB",
          direction: "BULLISH",
          confidence,
          reason: `Bullish order block at ${block.level.toFixed(2)} with strength ${block.strength.toFixed(1)}x`,
          entryPrice: current.close,
          stopPrice: block.level - atrVal,
          target1: current.close + atrVal * 2,
          target2: current.close + atrVal * 4,
        };
      }

      if (block.direction === "BEARISH" && current.close < block.level && isBearish(current)) {
        const confidence = Math.min(0.9, 0.65 + (1 - proximity) * 0.2 + Math.min(block.strength - 1, 0.5) * 0.1);
        return {
          setupType: "SMC_BEARISH_OB",
          direction: "BEARISH",
          confidence,
          reason: `Bearish order block at ${block.level.toFixed(2)} with strength ${block.strength.toFixed(1)}x`,
          entryPrice: current.close,
          stopPrice: block.level + atrVal,
          target1: current.close - atrVal * 2,
          target2: current.close - atrVal * 4,
        };
      }
    }
  }

  return null;
}
