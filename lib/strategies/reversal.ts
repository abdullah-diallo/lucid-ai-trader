import type { Candle, SignalResult } from "../types";
import { atr, rsi, isBullish, isBearish, bodySize } from "./utils";

function isHammer(c: Candle): boolean {
  const body = bodySize(c);
  const lowerWick = Math.min(c.open, c.close) - c.low;
  const upperWick = c.high - Math.max(c.open, c.close);
  return lowerWick >= body * 2 && upperWick < body * 0.5;
}

function isShootingStar(c: Candle): boolean {
  const body = bodySize(c);
  const upperWick = c.high - Math.max(c.open, c.close);
  const lowerWick = Math.min(c.open, c.close) - c.low;
  return upperWick >= body * 2 && lowerWick < body * 0.5;
}

function isEngulfing(prev: Candle, curr: Candle, bullish: boolean): boolean {
  if (bullish) {
    return isBearish(prev) && isBullish(curr) && curr.close > prev.open && curr.open < prev.close;
  }
  return isBullish(prev) && isBearish(curr) && curr.close < prev.open && curr.open > prev.close;
}

export function analyzeReversal(candles: Candle[]): SignalResult | null {
  if (candles.length < 15) return null;

  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const atrVal = atr(candles);
  const rsiVal = rsi(candles);

  // Bullish hammer at low RSI
  if (isHammer(current) && rsiVal < 40) {
    return {
      setupType: "REVERSAL_HAMMER_LONG",
      direction: "BULLISH",
      confidence: 0.67,
      reason: `Hammer reversal pattern at ${current.close.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.low - atrVal * 0.3,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Shooting star at high RSI
  if (isShootingStar(current) && rsiVal > 60) {
    return {
      setupType: "REVERSAL_STAR_SHORT",
      direction: "BEARISH",
      confidence: 0.67,
      reason: `Shooting star at ${current.close.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: current.high + atrVal * 0.3,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  // Bullish engulfing
  if (isEngulfing(prev, current, true) && rsiVal < 45) {
    return {
      setupType: "REVERSAL_ENGULF_LONG",
      direction: "BULLISH",
      confidence: 0.7,
      reason: `Bullish engulfing at ${current.close.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: prev.low - atrVal * 0.3,
      target1: current.close + atrVal * 2,
      target2: current.close + atrVal * 4,
    };
  }

  // Bearish engulfing
  if (isEngulfing(prev, current, false) && rsiVal > 55) {
    return {
      setupType: "REVERSAL_ENGULF_SHORT",
      direction: "BEARISH",
      confidence: 0.7,
      reason: `Bearish engulfing at ${current.close.toFixed(2)}, RSI ${rsiVal.toFixed(0)}`,
      entryPrice: current.close,
      stopPrice: prev.high + atrVal * 0.3,
      target1: current.close - atrVal * 2,
      target2: current.close - atrVal * 4,
    };
  }

  return null;
}
