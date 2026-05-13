import type { Candle } from "./types";

export const YF_SYMBOL_MAP: Record<string, string> = {
  "MES1!": "ES=F",
  "MNQ1!": "NQ=F",
  "M2K1!": "RTY=F",
  "MYM1!": "YM=F",
  "MGC1!": "GC=F",
  "MCL1!": "CL=F",
  "MBT1!": "BTC=F",
  "ES1!":  "ES=F",
  "NQ1!":  "NQ=F",
  "RTY1!": "RTY=F",
  "YM1!":  "YM=F",
  "GC1!":  "GC=F",
  "SI1!":  "SI=F",
  "CL1!":  "CL=F",
  "NG1!":  "NG=F",
  "HG1!":  "HG=F",
  "ZB1!":  "ZB=F",
  "ZN1!":  "ZN=F",
  "EURUSD": "EURUSD=X",
  "GBPUSD": "GBPUSD=X",
  "USDJPY": "JPY=X",
  "USDCHF": "CHF=X",
  "AUDUSD": "AUDUSD=X",
  "NZDUSD": "NZDUSD=X",
  "USDCAD": "CAD=X",
  "EURGBP": "EURGBP=X",
  "EURJPY": "EURJPY=X",
  "GBPJPY": "GBPJPY=X",
  "BTCUSD": "BTC-USD",
  "ETHUSD": "ETH-USD",
};

export const YF_INTERVAL_MAP: Record<string, string> = {
  "5m":  "5m",
  "15m": "15m",
  "1h":  "60m",
  "1d":  "1d",
};

// How many bars to request per timeframe
const BARS_NEEDED: Record<string, number> = {
  "5m":  80,
  "15m": 100,
  "1h":  100,
  "1d":  100,
};

// Seconds of lookback per timeframe (with 1.5x buffer for weekends/holidays)
const LOOKBACK_SECONDS: Record<string, number> = {
  "5m":  80  * 5  * 60 * 2,
  "15m": 100 * 15 * 60 * 2,
  "1h":  100 * 60 * 60 * 2,
  "1d":  100 * 24 * 60 * 60 * 1.5,
};

// Returns the Unix timestamp for today's US regular session open (9:30 AM ET = 13:30 UTC)
function todaySessionStart(): number {
  const now = new Date();
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 13, 30, 0));
  // If we're before 9:30 AM ET today, use yesterday's session
  if (Date.now() < d.getTime()) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return Math.floor(d.getTime() / 1000);
}

export async function fetchLiveCandles(symbol: string, timeframe: string): Promise<Candle[]> {
  const yfSymbol = YF_SYMBOL_MAP[symbol] ?? symbol;
  const interval = YF_INTERVAL_MAP[timeframe] ?? "60m";
  const now = Math.floor(Date.now() / 1000);

  let period1: number;
  if (timeframe === "5m") {
    // ORB: fetch from today's market open so the first bars are the opening range
    period1 = todaySessionStart();
  } else {
    period1 = now - (LOOKBACK_SECONDS[timeframe] ?? 7 * 24 * 3600);
  }

  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/` +
    `${encodeURIComponent(yfSymbol)}` +
    `?period1=${period1}&period2=${now}&interval=${interval}&events=history`;

  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json",
    },
    next: { revalidate: 0 },
  });

  if (!res.ok) throw new Error(`Yahoo Finance ${res.status} for ${yfSymbol}`);

  const json = await res.json();
  const result = json?.chart?.result?.[0];
  if (!result) return [];

  const timestamps: number[] = result.timestamp ?? [];
  const q = result.indicators?.quote?.[0] ?? {};

  return timestamps
    .map((t, i) => ({
      time: t,
      open:   (q.open?.[i]   ?? 0) as number,
      high:   (q.high?.[i]   ?? 0) as number,
      low:    (q.low?.[i]    ?? 0) as number,
      close:  (q.close?.[i]  ?? 0) as number,
      volume: (q.volume?.[i] ?? 0) as number,
    }))
    .filter(c => c.close > 0);
}

export function isMarketHours(): boolean {
  const now = new Date();
  const day = now.getUTCDay(); // 0=Sun 6=Sat
  if (day === 0 || day === 6) return false;
  const mins = now.getUTCHours() * 60 + now.getUTCMinutes();
  return mins >= 13 * 60 + 30 && mins < 20 * 60; // 9:30–4:00 PM ET
}

// Returns true if this timeframe's window is due to run (cron fires every 5 min)
export function isTimeframeDue(timeframe: string): boolean {
  const now = new Date();
  const mins = now.getUTCHours() * 60 + now.getUTCMinutes();
  switch (timeframe) {
    case "5m":  return true;
    case "15m": return mins % 15 < 5;
    case "1h":  return mins % 60 < 5;
    case "1d":  return mins >= 570 && mins < 575; // 9:30–9:35 AM ET (market open)
    default:    return false;
  }
}
