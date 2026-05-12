import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const list = query({
  args: {
    userId: v.string(),
    limit: v.optional(v.number()),
    status: v.optional(v.union(v.literal("open"), v.literal("closed"))),
  },
  handler: async (ctx, { userId, limit, status }) => {
    let q = ctx.db
      .query("trades")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc");
    const results = await q.collect();
    const filtered = status ? results.filter((t) => t.status === status) : results;
    return limit ? filtered.slice(0, limit) : filtered;
  },
});

export const add = mutation({
  args: {
    userId: v.string(),
    accountId: v.string(),
    symbol: v.string(),
    side: v.union(v.literal("Long"), v.literal("Short")),
    qty: v.number(),
    entryPrice: v.number(),
    strategy: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("trades", {
      ...args,
      status: "open",
      executedAt: Date.now(),
    });
  },
});

export const close = mutation({
  args: {
    tradeId: v.id("trades"),
    exitPrice: v.number(),
    pnl: v.number(),
  },
  handler: async (ctx, { tradeId, exitPrice, pnl }) => {
    await ctx.db.patch(tradeId, {
      exitPrice,
      pnl,
      status: "closed",
      closedAt: Date.now(),
    });
  },
});

export const getPnlStats = query({
  args: { userId: v.string(), dateRange: v.optional(v.string()) },
  handler: async (ctx, { userId, dateRange }) => {
    const allTrades = await ctx.db
      .query("trades")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.eq(q.field("status"), "closed"))
      .collect();

    let trades = allTrades;
    if (dateRange === "today") {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      trades = allTrades.filter((t) => t.executedAt >= start.getTime());
    } else if (dateRange === "week") {
      const start = new Date();
      start.setDate(start.getDate() - 7);
      trades = allTrades.filter((t) => t.executedAt >= start.getTime());
    } else if (dateRange === "month") {
      const start = new Date();
      start.setMonth(start.getMonth() - 1);
      trades = allTrades.filter((t) => t.executedAt >= start.getTime());
    }

    const wins = trades.filter((t) => (t.pnl ?? 0) > 0);
    const losses = trades.filter((t) => (t.pnl ?? 0) <= 0);
    const grossProfit = wins.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
    const grossLoss = Math.abs(losses.reduce((sum, t) => sum + (t.pnl ?? 0), 0));

    return {
      totalTrades: trades.length,
      wins: wins.length,
      losses: losses.length,
      winRate: trades.length > 0 ? wins.length / trades.length : 0,
      grossProfit,
      grossLoss,
      netPnl: grossProfit - grossLoss,
      avgWin: wins.length > 0 ? grossProfit / wins.length : 0,
      avgLoss: losses.length > 0 ? grossLoss / losses.length : 0,
      profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 999 : 0,
    };
  },
});

export const getByStrategy = query({
  args: { userId: v.string(), strategy: v.string(), dateRange: v.optional(v.string()) },
  handler: async (ctx, { userId, strategy, dateRange }) => {
    const trades = await ctx.db
      .query("trades")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) =>
        q.and(
          q.eq(q.field("status"), "closed"),
          q.eq(q.field("strategy"), strategy)
        )
      )
      .collect();

    let filtered = trades;
    if (dateRange === "today") {
      const start = new Date(); start.setHours(0, 0, 0, 0);
      filtered = trades.filter((t) => t.executedAt >= start.getTime());
    } else if (dateRange === "week") {
      const start = new Date(); start.setDate(start.getDate() - 7);
      filtered = trades.filter((t) => t.executedAt >= start.getTime());
    } else if (dateRange === "month") {
      const start = new Date(); start.setMonth(start.getMonth() - 1);
      filtered = trades.filter((t) => t.executedAt >= start.getTime());
    }

    const wins = filtered.filter((t) => (t.pnl ?? 0) > 0);
    const grossProfit = wins.reduce((s, t) => s + (t.pnl ?? 0), 0);
    const grossLoss = Math.abs(filtered.filter(t => (t.pnl ?? 0) < 0).reduce((s, t) => s + (t.pnl ?? 0), 0));

    return {
      strategy,
      totalTrades: filtered.length,
      winRate: filtered.length > 0 ? wins.length / filtered.length : 0,
      netPnl: grossProfit - grossLoss,
      grossProfit,
      grossLoss,
    };
  },
});
