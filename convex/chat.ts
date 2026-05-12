import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const listSessions = query({
  args: { userId: v.string() },
  handler: async (ctx, { userId }) => {
    return await ctx.db
      .query("chatSessions")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc")
      .collect();
  },
});

export const createSession = mutation({
  args: { userId: v.string(), title: v.optional(v.string()) },
  handler: async (ctx, { userId, title }) => {
    return await ctx.db.insert("chatSessions", {
      userId,
      title: title ?? `Chat ${new Date().toLocaleDateString()}`,
      updatedAt: Date.now(),
    });
  },
});

export const getSession = query({
  args: { sessionId: v.id("chatSessions") },
  handler: async (ctx, { sessionId }) => {
    const session = await ctx.db.get(sessionId);
    if (!session) return null;
    const messages = await ctx.db
      .query("chatMessages")
      .withIndex("by_session", (q) => q.eq("sessionId", sessionId))
      .collect();
    return { ...session, messages };
  },
});

export const addMessage = mutation({
  args: {
    sessionId: v.id("chatSessions"),
    userId: v.string(),
    role: v.union(v.literal("user"), v.literal("assistant")),
    content: v.string(),
  },
  handler: async (ctx, { sessionId, userId, role, content }) => {
    await ctx.db.insert("chatMessages", { sessionId, userId, role, content });
    await ctx.db.patch(sessionId, { updatedAt: Date.now() });
  },
});

export const deleteSession = mutation({
  args: { sessionId: v.id("chatSessions") },
  handler: async (ctx, { sessionId }) => {
    const messages = await ctx.db
      .query("chatMessages")
      .withIndex("by_session", (q) => q.eq("sessionId", sessionId))
      .collect();
    for (const msg of messages) {
      await ctx.db.delete(msg._id);
    }
    await ctx.db.delete(sessionId);
  },
});
