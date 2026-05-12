import { NextResponse } from "next/server";
import { getCurrentSession, getSessionLabel, timeUntilNextSession } from "@/lib/session-manager";

export async function GET() {
  const session = getCurrentSession();
  const label = getSessionLabel();
  const nextMs = timeUntilNextSession();
  const paperMode = process.env.PAPER_MODE === "true";

  return NextResponse.json({
    session,
    label,
    nextSessionMs: nextMs,
    paperMode,
  });
}
