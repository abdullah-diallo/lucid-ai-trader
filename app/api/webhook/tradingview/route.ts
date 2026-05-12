import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "crypto";
import { ConvexHttpClient } from "convex/browser";
import { api } from "@/convex/_generated/api";
import type { TradingSignal } from "@/lib/types";
import { routeSignal } from "@/lib/state-manager";

const convex = new ConvexHttpClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

function validateSecret(body: string, secret: string): boolean {
  const expected = createHmac("sha256", process.env.TRADINGVIEW_WEBHOOK_SECRET ?? "")
    .update(body)
    .digest("hex");
  return secret === expected || secret === process.env.TRADINGVIEW_WEBHOOK_SECRET;
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // Validate webhook secret
  const secret = (payload.secret as string) ?? "";
  if (!validateSecret(rawBody, secret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { symbol, action, price, timeframe, reason, strategy, confidence } = payload as Record<string, string | number>;

  if (!["BUY", "SELL", "CLOSE"].includes(String(action))) {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  const signal: TradingSignal = {
    symbol: String(symbol ?? "MES1!"),
    action: action as "BUY" | "SELL" | "CLOSE",
    price: Number(price ?? 0),
    timeframe: String(timeframe ?? "15m"),
    reason: String(reason ?? ""),
    strategy: strategy ? String(strategy) : undefined,
    confidence: confidence ? Number(confidence) : undefined,
  };

  // We need userId from the account — use a hardcoded system user for webhook context
  // In production, tie to a specific user account via webhook URL param or header
  const userId = req.nextUrl.searchParams.get("userId") ?? "system";

  // Store signal as pending
  const signalId = await convex.mutation(api.signals.add, {
    userId,
    symbol: signal.symbol,
    action: signal.action,
    price: signal.price,
    timeframe: signal.timeframe,
    reason: signal.reason,
    strategy: signal.strategy,
    confidence: signal.confidence,
    status: "pending",
  });

  // Get account and trading state for routing
  const [account, tradingState] = await Promise.all([
    convex.query(api.accounts.getActive, { userId }),
    convex.query(api.tradingState.get, { userId }),
  ]);

  if (!account) {
    await convex.mutation(api.signals.updateStatus, { signalId, status: "filtered" });
    return NextResponse.json({ ok: false, reason: "No active account" });
  }

  // Get daily trade count
  const performance = await convex.query(api.signals.getPerformance, { userId });
  const dailyCount = performance.total;

  const result = await routeSignal(
    signal,
    account as Parameters<typeof routeSignal>[1],
    tradingState.mode,
    dailyCount,
    signalId
  );

  await convex.mutation(api.signals.updateStatus, {
    signalId,
    status: result.action === "executed" ? "executed" : result.action === "pending_approval" ? "approved" : "filtered",
  });

  return NextResponse.json({ ok: true, ...result });
}
