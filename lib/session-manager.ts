import { toZonedTime, fromZonedTime } from "date-fns-tz";
import type { MarketSession } from "./types";

const ET = "America/New_York";

// High-impact economic events (hour in ET, 24h)
const ECONOMIC_EVENTS: Array<{ name: string; hour: number; minute: number; dayOfWeek?: number }> = [
  { name: "NFP", hour: 8, minute: 30, dayOfWeek: 5 },        // First Friday of month
  { name: "CPI", hour: 8, minute: 30 },
  { name: "PPI", hour: 8, minute: 30 },
  { name: "GDP", hour: 8, minute: 30 },
  { name: "FOMC", hour: 14, minute: 0 },
  { name: "Retail Sales", hour: 8, minute: 30 },
  { name: "Unemployment Claims", hour: 8, minute: 30, dayOfWeek: 4 },
  { name: "ISM Manufacturing", hour: 10, minute: 0 },
  { name: "Consumer Confidence", hour: 10, minute: 0 },
];

function getNowET(): Date {
  return toZonedTime(new Date(), ET);
}

export function getCurrentSession(): MarketSession {
  const now = getNowET();
  const dayOfWeek = now.getDay(); // 0=Sun, 6=Sat
  const h = now.getHours();
  const m = now.getMinutes();
  const timeMinutes = h * 60 + m;

  // Weekend: only Globex runs Sun evening
  if (dayOfWeek === 0) {
    return timeMinutes >= 20 * 60 ? "Globex" : "Closed";
  }
  if (dayOfWeek === 6) return "Closed";

  // Weekday session boundaries (all in ET minutes)
  const GLOBEX_OPEN = 20 * 60;   // 20:00
  const PREMARKET = 4 * 60;      // 04:00
  const RTH_OPEN = 9 * 60 + 30;  // 09:30
  const RTH_CLOSE = 16 * 60;     // 16:00
  const AH_CLOSE = 20 * 60;      // 20:00

  if (timeMinutes >= PREMARKET && timeMinutes < RTH_OPEN) return "Pre-market";
  if (timeMinutes >= RTH_OPEN && timeMinutes < RTH_CLOSE) return "RTH";
  if (timeMinutes >= RTH_CLOSE && timeMinutes < AH_CLOSE) return "AH";
  if (timeMinutes >= GLOBEX_OPEN || timeMinutes < PREMARKET) return "Globex";
  return "Closed";
}

export function isHighVolumeTime(): boolean {
  const now = getNowET();
  const h = now.getHours();
  const m = now.getMinutes();
  const t = h * 60 + m;
  // 09:30–11:30 or 14:00–16:00 ET
  return (t >= 9 * 60 + 30 && t < 11 * 60 + 30) || (t >= 14 * 60 && t < 16 * 60);
}

export function isNewsWindow(): boolean {
  const now = getNowET();
  const h = now.getHours();
  const m = now.getMinutes();
  const t = h * 60 + m;

  for (const event of ECONOMIC_EVENTS) {
    const eventMinutes = event.hour * 60 + event.minute;
    if (Math.abs(t - eventMinutes) <= 30) return true;
  }
  return false;
}

export function shouldTradeNow(): boolean {
  const now = getNowET();
  const dayOfWeek = now.getDay();
  if (dayOfWeek === 0 || dayOfWeek === 6) return false;
  const session = getCurrentSession();
  return session === "RTH" || session === "Pre-market" || session === "Globex";
}

export function timeUntilNextSession(): number {
  const now = getNowET();
  const h = now.getHours();
  const m = now.getMinutes();
  const t = h * 60 + m;

  const PREMARKET = 4 * 60;
  const RTH_OPEN = 9 * 60 + 30;
  const RTH_CLOSE = 16 * 60;
  const GLOBEX = 20 * 60;

  let nextMinutes: number;
  if (t < PREMARKET) nextMinutes = PREMARKET - t;
  else if (t < RTH_OPEN) nextMinutes = RTH_OPEN - t;
  else if (t < RTH_CLOSE) nextMinutes = RTH_CLOSE - t;
  else if (t < GLOBEX) nextMinutes = GLOBEX - t;
  else nextMinutes = (24 * 60 - t) + PREMARKET;

  return nextMinutes * 60 * 1000;
}

export function getSessionLabel(): string {
  const session = getCurrentSession();
  const now = getNowET();
  const h = now.getHours().toString().padStart(2, "0");
  const m = now.getMinutes().toString().padStart(2, "0");
  return `${session} • ${h}:${m} ET`;
}
