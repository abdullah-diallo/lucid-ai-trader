import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { authTables } from "@convex-dev/auth/server";

export default defineSchema({
  ...authTables,
  signals: defineTable({
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
    receivedAt: v.number(),
  })
    .index("by_user", ["userId"])
    .index("by_user_status", ["userId", "status"]),

  trades: defineTable({
    userId: v.string(),
    accountId: v.string(),
    symbol: v.string(),
    side: v.union(v.literal("Long"), v.literal("Short")),
    qty: v.number(),
    entryPrice: v.number(),
    exitPrice: v.optional(v.number()),
    pnl: v.optional(v.number()),
    status: v.union(v.literal("open"), v.literal("closed")),
    strategy: v.optional(v.string()),
    executedAt: v.number(),
    closedAt: v.optional(v.number()),
  })
    .index("by_user", ["userId"])
    .index("by_account", ["accountId"])
    .index("by_user_status", ["userId", "status"]),

  accounts: defineTable({
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
    currentBalance: v.number(),
    dailyPnl: v.number(),
    totalPnl: v.number(),
    dailyLossLimit: v.number(),
    maxDrawdownPct: v.number(),
    maxContracts: v.number(),
    broker: v.union(v.literal("paper"), v.literal("tradovate"), v.literal("ibkr")),
    isActive: v.boolean(),
    autonomousMode: v.boolean(),
    peakBalance: v.number(),
  }).index("by_user", ["userId"]),

  strategyConfigs: defineTable({
    userId: v.string(),
    strategyId: v.string(),
    enabled: v.boolean(),
  })
    .index("by_user", ["userId"])
    .index("by_user_strategy", ["userId", "strategyId"]),

  tvAccounts: defineTable({
    userId: v.string(),
    tvUsername: v.string(),
    symbol: v.string(),
    interval: v.string(),
    theme: v.union(v.literal("dark"), v.literal("light")),
    isActive: v.boolean(),
  }).index("by_user", ["userId"]),

  chatSessions: defineTable({
    userId: v.string(),
    title: v.string(),
    updatedAt: v.number(),
  }).index("by_user", ["userId"]),

  chatMessages: defineTable({
    sessionId: v.id("chatSessions"),
    userId: v.string(),
    role: v.union(v.literal("user"), v.literal("assistant")),
    content: v.string(),
  }).index("by_session", ["sessionId"]),

  tradeablePairs: defineTable({
    userId: v.string(),
    symbol: v.string(),
    enabled: v.boolean(),
  }).index("by_user", ["userId"]),

  tradingState: defineTable({
    userId: v.string(),
    mode: v.union(
      v.literal("FULL_AUTO"),
      v.literal("SEMI_AUTO"),
      v.literal("SIGNALS_ONLY")
    ),
    isPaused: v.boolean(),
    updatedAt: v.number(),
  }).index("by_user", ["userId"]),
});
