import { NextRequest, NextResponse } from "next/server";
import * as brokerRegistry from "@/lib/broker-registry";

export async function POST(req: NextRequest, { params }: { params: { name: string } }) {
  const { name } = params;
  const url = new URL(req.url);
  const action = url.searchParams.get("action") ?? "connect";
  const body = await req.json().catch(() => ({}));

  if (name === "paper") {
    if (action === "connect") {
      brokerRegistry.connectPaper();
      return NextResponse.json({ ok: true });
    }
    if (action === "disconnect") {
      brokerRegistry.disconnectPaper();
      return NextResponse.json({ ok: true });
    }
    if (action === "set-balance") {
      const amount = Number(body.balance);
      if (!amount || amount <= 0) return NextResponse.json({ error: "Invalid balance" }, { status: 400 });
      brokerRegistry.setPaperBalance(amount);
      return NextResponse.json({ ok: true });
    }
    if (action === "reset") {
      brokerRegistry.resetPaper();
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  }

  if (action === "connect") {
    const result = await brokerRegistry.connect(name as "tradovate", body);
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

export async function GET(req: NextRequest, { params }: { params: { name: string } }) {
  const { name } = params;
  if (name === "paper") {
    const status = await brokerRegistry.getPaperStatus();
    return NextResponse.json(status);
  }
  const brokers = await brokerRegistry.listAll();
  return NextResponse.json(brokers);
}
