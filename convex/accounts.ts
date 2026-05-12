import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const getActive = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    return await ctx.db
      .query("accounts")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.eq(q.field("isActive"), true))
      .first();
  },
});

export const list = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    return await ctx.db
      .query("accounts")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();
  },
});

export const create = mutation({
  args: {
    userId: v.string(),
    name: v.string(),
    accountType: v.union(
      v.literal("PROP_FIRM"),
      v.literal("PERSONAL_LIVE"),
      v.literal("DEMO"),
      v.literal("MANUAL")
    ),
    riskMode: v.union(
      v.literal("PROTECTED"),
      v.literal("BALANCED"),
      v.literal("FREE"),
      v.literal("SIMULATION")
    ),
    tradingMode: v.union(
      v.literal("FULL_AUTO"),
      v.literal("SEMI_AUTO"),
      v.literal("SIGNALS_ONLY")
    ),
    startingBalance: v.number(),
    dailyLossLimit: v.number(),
    maxDrawdownPct: v.number(),
    maxContracts: v.number(),
    broker: v.union(v.literal("paper"), v.literal("tradovate"), v.literal("ibkr")),
  },
  handler: async (ctx, args) => {
    // deactivate existing accounts for this user
    const existing = await ctx.db
      .query("accounts")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .collect();
    for (const acc of existing) {
      await ctx.db.patch(acc._id, { isActive: false });
    }
    return await ctx.db.insert("accounts", {
      ...args,
      currentBalance: args.startingBalance,
      dailyPnl: 0,
      totalPnl: 0,
      peakBalance: args.startingBalance,
      isActive: true,
      autonomousMode: false,
    });
  },
});

export const switchActive = mutation({
  args: { userId: v.string(), accountId: v.id("accounts") },
  handler: async (ctx, { userId, accountId }) => {
    const accounts = await ctx.db
      .query("accounts")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();
    for (const acc of accounts) {
      await ctx.db.patch(acc._id, { isActive: acc._id === accountId });
    }
  },
});

export const updateBalance = mutation({
  args: {
    accountId: v.id("accounts"),
    newBalance: v.number(),
    dailyPnl: v.number(),
    totalPnl: v.number(),
  },
  handler: async (ctx, { accountId, newBalance, dailyPnl, totalPnl }) => {
    const acc = await ctx.db.get(accountId);
    if (!acc) return;
    const peakBalance = Math.max(acc.peakBalance, newBalance);
    await ctx.db.patch(accountId, { currentBalance: newBalance, dailyPnl, totalPnl, peakBalance });
  },
});

export const toggleAutonomous = mutation({
  args: { accountId: v.id("accounts"), enabled: v.boolean() },
  handler: async (ctx, { accountId, enabled }) => {
    await ctx.db.patch(accountId, { autonomousMode: enabled });
  },
});
