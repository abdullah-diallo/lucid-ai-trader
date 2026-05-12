export { analyzeOrb } from "./orb";
export { analyzeSmc } from "./smc";
export { analyzeBreakRetest } from "./break-retest";
export { analyzeLiquiditySweep } from "./liquidity-sweep";
export { analyzeMeanReversion } from "./mean-reversion";
export { analyzeFibonacci } from "./fibonacci";
export { analyzeVwap } from "./vwap";
export { analyzeFading } from "./fading";
export { analyzeRange } from "./range";
export { analyzeAsiaRange } from "./asia-range";
export { analyzeNewsSpike } from "./news-spike";
export { analyzeGapAndGo } from "./gap-and-go";
export { analyzeBos } from "./bos";
export { analyzeMomentum } from "./momentum";
export { analyzeBreakout } from "./breakout";
export { analyzeScalping } from "./scalping";
export { analyzeTrendFollowing } from "./trend-following";
export { analyzeReversal } from "./reversal";
export { analyzeAmd } from "./amd";
export { analyzeIctSmc } from "./ict-smc";
export { analyzeConfluence } from "./confluence";

import type { Candle, SignalResult } from "../types";
import { analyzeOrb } from "./orb";
import { analyzeSmc } from "./smc";
import { analyzeBreakRetest } from "./break-retest";
import { analyzeLiquiditySweep } from "./liquidity-sweep";
import { analyzeMeanReversion } from "./mean-reversion";
import { analyzeFibonacci } from "./fibonacci";
import { analyzeVwap } from "./vwap";
import { analyzeFading } from "./fading";
import { analyzeRange } from "./range";
import { analyzeAsiaRange } from "./asia-range";
import { analyzeNewsSpike } from "./news-spike";
import { analyzeGapAndGo } from "./gap-and-go";
import { analyzeBos } from "./bos";
import { analyzeMomentum } from "./momentum";
import { analyzeBreakout } from "./breakout";
import { analyzeScalping } from "./scalping";
import { analyzeTrendFollowing } from "./trend-following";
import { analyzeReversal } from "./reversal";
import { analyzeAmd } from "./amd";
import { analyzeIctSmc } from "./ict-smc";
import { analyzeConfluence } from "./confluence";

const STRATEGY_MAP: Record<string, (candles: Candle[]) => SignalResult | null> = {
  ORB: analyzeOrb,
  SMC: analyzeSmc,
  BREAK_RETEST: analyzeBreakRetest,
  LIQUIDITY_SWEEP: analyzeLiquiditySweep,
  MEAN_REVERSION: analyzeMeanReversion,
  FIBONACCI: analyzeFibonacci,
  VWAP: analyzeVwap,
  FADING: analyzeFading,
  RANGE: analyzeRange,
  ASIA_RANGE: analyzeAsiaRange,
  NEWS_SPIKE: analyzeNewsSpike,
  GAP_AND_GO: analyzeGapAndGo,
  BOS: analyzeBos,
  MOMENTUM: analyzeMomentum,
  BREAKOUT: analyzeBreakout,
  SCALPING: analyzeScalping,
  TREND_FOLLOWING: analyzeTrendFollowing,
  REVERSAL: analyzeReversal,
  AMD: analyzeAmd,
  ICT_SMC: analyzeIctSmc,
  CONFLUENCE: analyzeConfluence,
};

export function runStrategy(strategyId: string, candles: Candle[]): SignalResult | null {
  const fn = STRATEGY_MAP[strategyId];
  return fn ? fn(candles) : null;
}

export function runAllStrategies(candles: Candle[], enabledIds: string[]): SignalResult[] {
  return enabledIds
    .map((id) => runStrategy(id, candles))
    .filter(Boolean) as SignalResult[];
}
