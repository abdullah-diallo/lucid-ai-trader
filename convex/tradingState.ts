import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const get = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    const state = await ctx.db
      .query("tradingState")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .first();
    return state ?? { mode: "FULL_AUTO" as const, isPaused: false };
  },
});

export const setMode = mutation({
  args: {
    userId: v.string(),
    mode: v.union(
      v.literal("FULL_AUTO"),
      v.literal("SEMI_AUTO"),
      v.literal("SIGNALS_ONLY")
    ),
  },
  handler: async (ctx, { userId, mode }) => {
    const existing = await ctx.db
      .query("tradingState")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, { mode, updatedAt: Date.now() });
    } else {
      await ctx.db.insert("tradingState", { userId, mode, isPaused: false, updatedAt: Date.now() });
    }
  },
});

export const setPaused = mutation({
  args: { userId: v.string(), isPaused: v.boolean() },
  handler: async (ctx, { userId, isPaused }) => {
    const existing = await ctx.db
      .query("tradingState")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .first();
    if (existing) {
      await ctx.db.patch(existing._id, { isPaused, updatedAt: Date.now() });
    } else {
      await ctx.db.insert("tradingState", {
        userId,
        mode: "FULL_AUTO",
        isPaused,
        updatedAt: Date.now(),
      });
    }
  },
});
