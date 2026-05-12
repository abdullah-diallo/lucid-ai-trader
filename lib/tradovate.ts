import type { OrderResult, Position } from "./types";

interface TradovateToken {
  accessToken: string;
  expiresAt: number;
}

let _token: TradovateToken | null = null;

const BASE_URL = process.env.TRADOVATE_API_BASE_URL ?? "https://demo-api.tradovate.com";

async function request<T>(
  path: string,
  method: "GET" | "POST" = "GET",
  body?: unknown
): Promise<T> {
  const token = await getAccessToken();
  const res = await fetch(`${BASE_URL}/v1${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`Tradovate ${method} ${path} → ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function getAccessToken(): Promise<string> {
  // Refresh 60s before expiry
  if (_token && Date.now() < _token.expiresAt - 60_000) {
    return _token.accessToken;
  }

  const res = await fetch(`${BASE_URL}/v1/auth/accesstokenrequest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: process.env.TRADOVATE_USERNAME,
      password: process.env.TRADOVATE_PASSWORD,
      appId: process.env.TRADOVATE_CLIENT_ID,
      appVersion: "1.0",
      cid: process.env.TRADOVATE_CLIENT_ID,
      sec: process.env.TRADOVATE_CLIENT_SECRET,
    }),
  });

  if (!res.ok) throw new Error(`Tradovate auth failed: ${res.status}`);
  const data = (await res.json()) as { accessToken: string; expirationTime: string };
  _token = {
    accessToken: data.accessToken,
    expiresAt: new Date(data.expirationTime).getTime(),
  };
  return _token.accessToken;
}

export async function placeOrder(
  symbol: string,
  qty: number,
  action: "Buy" | "Sell"
): Promise<OrderResult> {
  try {
    const data = await request<{ orderId: number }>("/order/placeorder", "POST", {
      accountSpec: process.env.TRADOVATE_USERNAME,
      symbol,
      orderQty: qty,
      orderType: "Market",
      action,
    });
    return { ok: true, orderId: String(data.orderId), message: `Order placed: ${action} ${qty} ${symbol}` };
  } catch (err) {
    return { ok: false, message: String(err) };
  }
}

export async function liquidatePosition(positionId: number): Promise<OrderResult> {
  try {
    await request("/order/liquidateposition", "POST", { positionId, adminAction: false });
    return { ok: true, message: "Position liquidated" };
  } catch (err) {
    return { ok: false, message: String(err) };
  }
}

export async function getPositions(): Promise<Position[]> {
  try {
    const data = await request<Array<{ id: number; symbol: string; netPos: number; avgPrice: number }>>("/position/list");
    return data
      .filter((p) => p.netPos !== 0)
      .map((p) => ({
        symbol: p.symbol,
        qty: Math.abs(p.netPos),
        side: p.netPos > 0 ? ("Long" as const) : ("Short" as const),
        entryPrice: p.avgPrice,
        currentPnl: 0,
      }));
  } catch {
    return [];
  }
}

export async function getAccountBalance(): Promise<number> {
  try {
    const accounts = await request<Array<{ id: number; balance: number }>>("/account/list");
    return accounts[0]?.balance ?? 0;
  } catch {
    return 0;
  }
}

export function clearToken(): void {
  _token = null;
}
