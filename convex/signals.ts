import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const list = query({
  args: { userId: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, { userId, limit }) => {
    const q = ctx.db
      .query("signals")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc");
    return limit ? await q.take(limit) : await q.collect();
  },
});

export const add = mutation({
  args: {
    userId: v.string(),
    symbol: v.string(),
    action: v.union(v.literal("BUY"), v.literal("SELL"), v.literal("CLOSE")),
    price: v.number(),
    timeframe: v.string(),
    reason: v.string(),
    strategy: v.optional(v.string()),
    confidence: v.optional(v.number()),
    status: v.union(
      v.literal("pending"),
      v.literal("approved"),
      v.literal("rejected"),
      v.literal("executed"),
      v.literal("filtered")
    ),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("signals", { ...args, receivedAt: Date.now() });
  },
});

export const getPending = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    return await ctx.db
      .query("signals")
      .withIndex("by_user_status", (q) =>
        q.eq("userId", userId).eq("status", "pending")
      )
      .order("desc")
      .first();
  },
});

export const updateStatus = mutation({
  args: {
    signalId: v.id("signals"),
    status: v.union(
      v.literal("approved"),
      v.literal("rejected"),
      v.literal("executed"),
      v.literal("filtered")
    ),
  },
  handler: async (ctx, { signalId, status }) => {
    await ctx.db.patch(signalId, { status });
  },
});

export const getPerformance = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const signals = await ctx.db
      .query("signals")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .filter((q) => q.gte(q.field("receivedAt"), today.getTime()))
      .collect();
    return {
      buy: signals.filter((s) => s.action === "BUY").length,
      sell: signals.filter((s) => s.action === "SELL").length,
      close: signals.filter((s) => s.action === "CLOSE").length,
      filtered: signals.filter((s) => s.status === "filtered").length,
      total: signals.length,
    };
  },
});
