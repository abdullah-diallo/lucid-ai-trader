import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

const DEFAULT_PAIRS = [
  "MES1!", "MNQ1!", "ES1!", "NQ1!", "RTY1!", "YM1!", "GC1!", "CL1!",
  "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "EURUSD", "GBPUSD",
];

export const list = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const saved = await ctx.db
      .query("tradeablePairs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();

    if (saved.length === 0) {
      return DEFAULT_PAIRS.map((symbol) => ({ symbol, enabled: true }));
    }
    return saved.map(({ symbol, enabled }) => ({ symbol, enabled }));
  },
});

export const toggle = mutation({
  args: { userId: v.string(), symbol: v.string(), enabled: v.boolean() },
  handler: async (ctx, { userId, symbol, enabled }) => {
    const existing = await ctx.db
      .query("tradeablePairs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.eq(q.field("symbol"), symbol))
      .first();

    if (existing) {
      await ctx.db.patch(existing._id, { enabled });
    } else {
      await ctx.db.insert("tradeablePairs", { userId, symbol, enabled });
    }
  },
});

export const initDefaults = mutation({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const existing = await ctx.db
      .query("tradeablePairs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();

    if (existing.length === 0) {
      for (const symbol of DEFAULT_PAIRS) {
        await ctx.db.insert("tradeablePairs", { userId, symbol, enabled: true });
      }
    }
  },
});
