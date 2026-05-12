import { NextRequest, NextResponse } from "next/server";
import * as brokerRegistry from "@/lib/broker-registry";

export async function POST(req: NextRequest, { params }: { params: { name: string } }) {
  const { name } = params;
  const url = new URL(req.url);
  const action = url.searchParams.get("action") ?? "connect";

  if (action === "connect") {
    const body = await req.json().catch(() => ({}));
    const result = await brokerRegistry.connect(name as "paper" | "tradovate", body);
    return NextResponse.json(result);
  }

  if (action === "activate") {
    brokerRegistry.switchTo(name as "paper" | "tradovate");
    return NextResponse.json({ ok: true });
  }

  if (action === "disconnect") {
    brokerRegistry.disconnect(name as "paper" | "tradovate");
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "Unknown action" }, { status: 400 });
}

export async function GET() {
  const brokers = await brokerRegistry.listAll();
  return NextResponse.json(brokers);
}
