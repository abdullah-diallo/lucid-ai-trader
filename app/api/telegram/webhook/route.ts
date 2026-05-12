import { NextRequest, NextResponse } from "next/server";
import { handleCallbackQuery, sendMessage } from "@/lib/telegram";

export async function POST(req: NextRequest) {
  const update = await req.json();

  if (update.callback_query) {
    handleCallbackQuery(update.callback_query.data as string);
    return NextResponse.json({ ok: true });
  }

  if (update.message?.text) {
    const text = update.message.text as string;

    if (text === "/status") {
      const { getCurrentSession, getSessionLabel } = await import("@/lib/session-manager");
      await sendMessage(`📊 <b>Status</b>\nSession: ${getSessionLabel()}\nPaper Mode: ${process.env.PAPER_MODE === "true" ? "ON" : "OFF"}`);
    } else if (text === "/help") {
      await sendMessage("📖 <b>Commands</b>\n/status — session + mode\n/help — this list");
    }
  }

  return NextResponse.json({ ok: true });
}
