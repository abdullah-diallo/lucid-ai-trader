import Groq from "groq-sdk";
import type { TradingSignal, PnlStats } from "./types";

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

const MODEL = "llama-3.3-70b-versatile";

export async function analyzeSignal(signal: TradingSignal): Promise<string> {
  const prompt = `You are a professional futures trading analyst. Analyze this trading signal and provide a 2-3 sentence commentary on the setup quality, key levels to watch, and confidence:

Signal: ${signal.action} ${signal.symbol}
Price: ${signal.price}
Timeframe: ${signal.timeframe}
Strategy: ${signal.strategy ?? "Unknown"}
Confidence: ${((signal.confidence ?? 0) * 100).toFixed(0)}%
Reason: ${signal.reason}

Be concise and professional. Focus on actionable insight.`;

  const response = await groq.chat.completions.create({
    model: MODEL,
    messages: [{ role: "user", content: prompt }],
    max_tokens: 200,
    temperature: 0.3,
  });

  return response.choices[0]?.message?.content ?? "Unable to analyze signal.";
}

export async function analyzePnl(stats: PnlStats): Promise<string> {
  const prompt = `You are a trading performance coach. Analyze this trading session performance and provide 1 actionable improvement tip:

Total Trades: ${stats.totalTrades}
Win Rate: ${(stats.winRate * 100).toFixed(1)}%
Net P&L: $${stats.netPnl.toFixed(2)}
Gross Profit: $${stats.grossProfit.toFixed(2)}
Gross Loss: $${stats.grossLoss.toFixed(2)}
Profit Factor: ${stats.profitFactor.toFixed(2)}
Avg Win: $${stats.avgWin.toFixed(2)}
Avg Loss: $${stats.avgLoss.toFixed(2)}

Give a brief assessment (2-3 sentences) then 1 specific, actionable tip.`;

  const response = await groq.chat.completions.create({
    model: MODEL,
    messages: [{ role: "user", content: prompt }],
    max_tokens: 250,
    temperature: 0.4,
  });

  return response.choices[0]?.message?.content ?? "Unable to analyze performance.";
}

export async function chat(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  systemPrompt?: string
): Promise<string> {
  const response = await groq.chat.completions.create({
    model: MODEL,
    messages: [
      {
        role: "system",
        content:
          systemPrompt ??
          "You are Lucid AI, an expert futures trading assistant specializing in ES/MES, NQ/MNQ, and RTY. You help traders analyze setups, manage risk, and improve performance. Be concise and practical.",
      },
      ...messages,
    ],
    max_tokens: 1000,
    temperature: 0.5,
  });

  return response.choices[0]?.message?.content ?? "Unable to respond.";
}

export async function* chatStream(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  systemPrompt?: string
): AsyncGenerator<string> {
  const stream = await groq.chat.completions.create({
    model: MODEL,
    messages: [
      {
        role: "system",
        content:
          systemPrompt ??
          "You are Lucid AI, an expert futures trading assistant. Be concise and practical.",
      },
      ...messages,
    ],
    max_tokens: 1000,
    temperature: 0.5,
    stream: true,
  });

  for await (const chunk of stream) {
    const text = chunk.choices[0]?.delta?.content;
    if (text) yield text;
  }
}
