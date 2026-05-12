import TelegramBot from "node-telegram-bot-api";
import type { TradingSignal } from "./types";

let bot: TelegramBot | null = null;
const CHAT_ID = process.env.TELEGRAM_CHAT_ID ?? "";

// Pending approval callbacks: signalId → resolve function
const pendingApprovals = new Map<string, (approved: boolean) => void>();

export function getBot(): TelegramBot | null {
  if (!process.env.TELEGRAM_BOT_TOKEN) return null;
  if (!bot) {
    bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN);
  }
  return bot;
}

export async function setupWebhook(url: string): Promise<void> {
  const b = getBot();
  if (!b) return;
  await b.setWebHook(`${url}/api/telegram/webhook`);
}

export async function sendMessage(text: string): Promise<void> {
  const b = getBot();
  if (!b || !CHAT_ID) return;
  try {
    await b.sendMessage(CHAT_ID, text, { parse_mode: "HTML" });
  } catch (err) {
    console.error("Telegram sendMessage error:", err);
  }
}

export async function sendSignalApproval(
  signalId: string,
  signal: TradingSignal
): Promise<boolean> {
  const b = getBot();
  if (!b || !CHAT_ID) return true; // auto-approve if Telegram not configured

  const text =
    `🔔 <b>Signal Approval Required</b>\n\n` +
    `Action: <b>${signal.action}</b> ${signal.symbol}\n` +
    `Price: ${signal.price}\n` +
    `Timeframe: ${signal.timeframe}\n` +
    `Strategy: ${signal.strategy ?? "N/A"}\n` +
    `Confidence: ${((signal.confidence ?? 0) * 100).toFixed(0)}%\n` +
    `Reason: ${signal.reason}\n\n` +
    `⏱ Timeout: 60 seconds`;

  await b.sendMessage(CHAT_ID, text, {
    parse_mode: "HTML",
    reply_markup: {
      inline_keyboard: [
        [
          { text: "✅ Approve", callback_data: `approve:${signalId}` },
          { text: "❌ Reject", callback_data: `reject:${signalId}` },
        ],
      ],
    },
  });

  return new Promise<boolean>((resolve) => {
    pendingApprovals.set(signalId, resolve);
    // Auto-reject after 60s
    setTimeout(() => {
      if (pendingApprovals.has(signalId)) {
        pendingApprovals.delete(signalId);
        resolve(false);
      }
    }, 60_000);
  });
}

export function handleCallbackQuery(data: string): void {
  const [action, signalId] = data.split(":");
  const resolver = pendingApprovals.get(signalId);
  if (resolver) {
    pendingApprovals.delete(signalId);
    resolver(action === "approve");
  }
}

export async function sendRiskAlert(haltLevel: number, message: string): Promise<void> {
  const emoji = haltLevel >= 4 ? "🚨" : haltLevel >= 2 ? "⚠️" : "ℹ️";
  await sendMessage(`${emoji} <b>Risk Alert (Level ${haltLevel})</b>\n${message}`);
}

export async function sendTradeAlert(
  action: string,
  symbol: string,
  qty: number,
  price: number
): Promise<void> {
  const emoji = action === "BUY" ? "🟢" : action === "SELL" ? "🔴" : "🟠";
  await sendMessage(
    `${emoji} <b>Trade Executed</b>\n${action} ${qty}x ${symbol} @ ${price}`
  );
}
