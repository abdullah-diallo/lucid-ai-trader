import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { ConvexHttpClient } from "convex/browser";
import { api } from "@/convex/_generated/api";
import * as brokerRegistry from "@/lib/broker-registry";

const convex = new ConvexHttpClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { symbol, action, price, reason } = await req.json() as {
    symbol: string;
    action: "BUY" | "SELL" | "CLOSE";
    price?: number;
    reason?: string;
  };

  const signalId = await convex.mutation(api.signals.add, {
    userId,
    symbol,
    action,
    price: price ?? 0,
    timeframe: "manual",
    reason: reason ?? "Manual trade",
    status: "approved",
  });

  const qty = parseInt(process.env.ORDER_QTY ?? "1", 10);

  let result;
  if (action === "CLOSE") {
    result = await brokerRegistry.closePosition(symbol);
  } else {
    result = await brokerRegistry.placeOrder(symbol, qty, action === "BUY" ? "Buy" : "Sell");
  }

  await convex.mutation(api.signals.updateStatus, {
    signalId,
    status: result.ok ? "executed" : "filtered",
  });

  return NextResponse.json({ ok: result.ok, message: result.message });
}
