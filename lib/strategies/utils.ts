import type { Candle } from "../types";

export function atr(candles: Candle[], period = 14): number {
  if (candles.length < period + 1) return 0;
  const trValues = candles.slice(1).map((c, i) => {
    const prev = candles[i];
    return Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close));
  });
  const slice = trValues.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / slice.length;
}

export function ema(candles: Candle[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [];
  let prev = candles[0].close;
  for (const c of candles) {
    const val = c.close * k + prev * (1 - k);
    result.push(val);
    prev = val;
  }
  return result;
}

export function sma(candles: Candle[], period: number): number {
  const slice = candles.slice(-period);
  return slice.reduce((s, c) => s + c.close, 0) / slice.length;
}

export function vwap(candles: Candle[]): number {
  let cumTP = 0, cumVol = 0;
  for (const c of candles) {
    const tp = (c.high + c.low + c.close) / 3;
    cumTP += tp * c.volume;
    cumVol += c.volume;
  }
  return cumVol > 0 ? cumTP / cumVol : 0;
}

export function pivotHigh(candles: Candle[], lookback = 5): number | null {
  if (candles.length < lookback * 2 + 1) return null;
  const mid = candles[candles.length - lookback - 1];
  const left = candles.slice(-lookback * 2 - 1, -lookback - 1);
  const right = candles.slice(-lookback);
  if (left.every((c) => c.high < mid.high) && right.every((c) => c.high < mid.high)) {
    return mid.high;
  }
  return null;
}

export function pivotLow(candles: Candle[], lookback = 5): number | null {
  if (candles.length < lookback * 2 + 1) return null;
  const mid = candles[candles.length - lookback - 1];
  const left = candles.slice(-lookback * 2 - 1, -lookback - 1);
  const right = candles.slice(-lookback);
  if (left.every((c) => c.low > mid.low) && right.every((c) => c.low > mid.low)) {
    return mid.low;
  }
  return null;
}

export function highestHigh(candles: Candle[], period: number): number {
  return Math.max(...candles.slice(-period).map((c) => c.high));
}

export function lowestLow(candles: Candle[], period: number): number {
  return Math.min(...candles.slice(-period).map((c) => c.low));
}

export function rsi(candles: Candle[], period = 14): number {
  if (candles.length < period + 1) return 50;
  const changes = candles.slice(1).map((c, i) => c.close - candles[i].close);
  const recent = changes.slice(-period);
  const gains = recent.filter((x) => x > 0);
  const losses = recent.filter((x) => x < 0).map(Math.abs);
  const avgGain = gains.reduce((a, b) => a + b, 0) / period;
  const avgLoss = losses.reduce((a, b) => a + b, 0) / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

export function bodySize(c: Candle): number {
  return Math.abs(c.close - c.open);
}

export function isBullish(c: Candle): boolean {
  return c.close > c.open;
}

export function isBearish(c: Candle): boolean {
  return c.close < c.open;
}

export function clamp(val: number, min: number, max: number): number {
  return Math.min(Math.max(val, min), max);
}
