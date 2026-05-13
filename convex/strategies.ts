import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

// All known strategies with metadata
export const STRATEGY_REGISTRY = [
  { id: "ORB",            name: "Opening Range Breakout",  description: "First 15-minute range breakout continuation",         timeframe: "5m"  },
  { id: "SMC",            name: "Smart Money Concepts",    description: "Order blocks, liquidity sweeps, fair value gaps",      timeframe: "1h"  },
  { id: "BREAK_RETEST",   name: "Break & Retest",          description: "Breakout + pullback to broken level + continuation",   timeframe: "1h"  },
  { id: "LIQUIDITY_SWEEP",name: "Liquidity Sweep",         description: "Synthetic order block sweep entries",                  timeframe: "15m" },
  { id: "MEAN_REVERSION", name: "Mean Reversion",          description: "Revert to moving average after extension",            timeframe: "1h"  },
  { id: "FIBONACCI",      name: "Fibonacci Retracement",   description: "Fib-level bounce setups (0.618, 0.786)",              timeframe: "1h"  },
  { id: "VWAP",           name: "VWAP Strategy",           description: "Volume-weighted average price reclaim/rejection",     timeframe: "15m" },
  { id: "FADING",         name: "Fading",                  description: "Counter-trend pullback entries",                      timeframe: "1h"  },
  { id: "RANGE",          name: "Range Trading",           description: "Support/resistance range bound entries",              timeframe: "1h"  },
  { id: "ASIA_RANGE",     name: "Asia Range",              description: "Asia session range continuation into RTH",            timeframe: "1h"  },
  { id: "NEWS_SPIKE",     name: "News Spike",              description: "Post-news volatility directional entries",            timeframe: "15m" },
  { id: "GAP_AND_GO",     name: "Gap & Go",                description: "Opening gap continuation momentum",                  timeframe: "1h"  },
  { id: "BOS",            name: "Break of Structure",      description: "ICT/SMC structure break confirmation entries",        timeframe: "1h"  },
  { id: "MOMENTUM",       name: "Momentum",                description: "Directional momentum continuation",                  timeframe: "1h"  },
  { id: "BREAKOUT",       name: "Breakout",                description: "New high/low breakout entries",                      timeframe: "1h"  },
  { id: "SCALPING",       name: "Scalping",                description: "Quick short-term entries via TradingView alerts",    timeframe: "tv"  },
  { id: "TREND_FOLLOWING",name: "Trend Following",         description: "Directional trend pullback entries",                 timeframe: "1h"  },
  { id: "REVERSAL",       name: "Reversal",                description: "Reversal candle pattern entries",                    timeframe: "1d"  },
  { id: "AMD",            name: "AMD Distribution",        description: "Accumulation/Manipulation/Distribution zone trading", timeframe: "1h"  },
  { id: "ICT_SMC",        name: "ICT/SMC Engine",          description: "Full ICT model with killzones and order flow",       timeframe: "15m" },
  { id: "CONFLUENCE",     name: "Confluence Scorer",       description: "Multi-confluence signal strength entries",           timeframe: "1h"  },
  { id: "HIGH_CONVICTION",name: "High Conviction",         description: "High confidence setups — 4+ conditions aligned",    timeframe: "1h"  },
  { id: "PROBABILITY",    name: "Probability Engine",      description: "Win probability weighted entries",                   timeframe: "1h"  },
  { id: "NEWS_SENTIMENT", name: "News Sentiment",          description: "Volume-spike event detection and directional setups", timeframe: "1d"  },
] as const;

export const listConfigs = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const configs = await ctx.db
      .query("strategyConfigs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();

    const configMap = new Map(configs.map((c) => [c.strategyId, c.enabled]));

    return STRATEGY_REGISTRY.map((s) => ({
      ...s,
      enabled: configMap.get(s.id) ?? true,
    }));
  },
});

export const toggle = mutation({
  args: {
    userId: v.string(),
    strategyId: v.string(),
    enabled: v.boolean(),
  },
  handler: async (ctx, { userId, strategyId, enabled }) => {
    const existing = await ctx.db
      .query("strategyConfigs")
      .withIndex("by_user_strategy", (q) =>
        q.eq("userId", userId).eq("strategyId", strategyId)
      )
      .first();

    if (existing) {
      await ctx.db.patch(existing._id, { enabled });
    } else {
      await ctx.db.insert("strategyConfigs", { userId, strategyId, enabled });
    }
  },
});

export const getEnabledIds = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const configs = await ctx.db
      .query("strategyConfigs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();

    const disabledSet = new Set(
      configs.filter((c) => !c.enabled).map((c) => c.strategyId)
    );

    return STRATEGY_REGISTRY.map((s) => s.id).filter((id) => !disabledSet.has(id));
  },
});
