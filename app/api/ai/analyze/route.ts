import { NextRequest, NextResponse } from "next/server";
import { analyzeSignal, analyzePnl } from "@/lib/groq";
import type { TradingSignal, PnlStats } from "@/lib/types";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { type, signal, pnlData } = body as {
    type: "signal" | "pnl";
    signal?: TradingSignal;
    pnlData?: PnlStats;
  };

  if (type === "signal" && signal) {
    const commentary = await analyzeSignal(signal);
    return NextResponse.json({ commentary });
  }

  if (type === "pnl" && pnlData) {
    const analysis = await analyzePnl(pnlData);
    return NextResponse.json({ analysis });
  }

  return NextResponse.json({ error: "Invalid request" }, { status: 400 });
}
