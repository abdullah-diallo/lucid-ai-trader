import type { OrderResult, Position, BrokerStatus } from "./types";
import * as tradovate from "./tradovate";

// ── Paper Broker (in-memory) ──────────────────────────────────────────────────
class PaperBroker {
  private startingBalance = 100_000;
  private balance = 100_000;
  private connected = true;
  private positions = new Map<string, { qty: number; side: "Long" | "Short"; entryPrice: number }>();

  connect() { this.connected = true; }
  disconnect() { this.connected = false; }
  isConnected() { return this.connected; }
  getStartingBalance() { return this.startingBalance; }

  setBalance(amount: number) {
    this.startingBalance = amount;
    this.balance = amount;
    this.positions.clear();
  }

  reset() {
    this.balance = this.startingBalance;
    this.positions.clear();
  }

  async placeOrder(symbol: string, qty: number, action: "Buy" | "Sell"): Promise<OrderResult> {
    this.positions.set(symbol, {
      qty,
      side: action === "Buy" ? "Long" : "Short",
      entryPrice: 0,
    });
    return { ok: true, message: `[PAPER] ${action} ${qty} ${symbol}` };
  }

  async closePosition(symbol: string): Promise<OrderResult> {
    this.positions.delete(symbol);
    return { ok: true, message: `[PAPER] Closed ${symbol}` };
  }

  async getBalance(): Promise<number> { return this.balance; }

  async getPositions(): Promise<Position[]> {
    return Array.from(this.positions.entries()).map(([symbol, p]) => ({
      symbol,
      qty: p.qty,
      side: p.side,
      entryPrice: p.entryPrice,
      currentPnl: 0,
    }));
  }
}

// ── Tradovate Broker ──────────────────────────────────────────────────────────
class TradovateBroker {
  private connected = false;

  async connect(creds: { username: string; password: string; clientId: string; clientSecret: string }): Promise<{ ok: boolean; message: string }> {
    try {
      await tradovate.getAccessToken();
      this.connected = true;
      return { ok: true, message: "Connected to Tradovate" };
    } catch (err) {
      return { ok: false, message: String(err) };
    }
  }

  isConnected(): boolean { return this.connected; }

  async placeOrder(symbol: string, qty: number, action: "Buy" | "Sell"): Promise<OrderResult> {
    return tradovate.placeOrder(symbol, qty, action);
  }

  async closePosition(symbol: string): Promise<OrderResult> {
    const positions = await tradovate.getPositions();
    const pos = positions.find((p) => p.symbol === symbol);
    if (!pos) return { ok: false, message: `No open position for ${symbol}` };
    return tradovate.liquidatePosition(0);
  }

  async getBalance(): Promise<number> { return tradovate.getAccountBalance(); }
  async getPositions(): Promise<Position[]> { return tradovate.getPositions(); }

  disconnect(): void {
    this.connected = false;
    tradovate.clearToken();
  }
}

// ── Registry Singleton ─────────────────────────────────────────────────────────
type BrokerName = "paper" | "tradovate";

const paper = new PaperBroker();
const tradovateBroker = new TradovateBroker();

let activeBroker: BrokerName = "paper";

export async function listAll(): Promise<BrokerStatus[]> {
  return [
    {
      name: "paper",
      connected: true,
      balance: await paper.getBalance(),
      positions: await paper.getPositions(),
      connectionFields: [],
    },
    {
      name: "tradovate",
      connected: tradovateBroker.isConnected(),
      connectionFields: [
        { key: "username", label: "Username", type: "text", required: true },
        { key: "password", label: "Password", type: "password", required: true },
        { key: "clientId", label: "Client ID", type: "text", required: true },
        { key: "clientSecret", label: "Client Secret", type: "password", required: true },
      ],
    },
  ];
}

export function getActiveName(): BrokerName { return activeBroker; }

export function connectPaper() { paper.connect(); activeBroker = "paper"; }
export function disconnectPaper() { paper.disconnect(); if (activeBroker === "paper") activeBroker = "paper"; }
export function setPaperBalance(amount: number) { paper.setBalance(amount); }
export function resetPaper() { paper.reset(); }
export async function getPaperStatus() {
  return {
    connected: paper.isConnected(),
    balance: await paper.getBalance(),
    startingBalance: paper.getStartingBalance(),
    positions: await paper.getPositions(),
  };
}

export async function connect(
  name: BrokerName,
  creds: Record<string, string>
): Promise<{ ok: boolean; message: string }> {
  if (name === "tradovate") {
    const result = await tradovateBroker.connect(creds as Parameters<typeof tradovateBroker.connect>[0]);
    if (result.ok) activeBroker = "tradovate";
    return result;
  }
  return { ok: false, message: `Unknown broker: ${name}` };
}

export function switchTo(name: BrokerName): void {
  activeBroker = name;
}

export function disconnect(name: BrokerName): void {
  if (name === "tradovate") tradovateBroker.disconnect();
  if (activeBroker === name) activeBroker = "paper";
}

export async function placeOrder(
  symbol: string,
  qty: number,
  action: "Buy" | "Sell"
): Promise<OrderResult> {
  if (process.env.PAPER_MODE === "true") {
    return paper.placeOrder(symbol, qty, action);
  }
  if (activeBroker === "tradovate") return tradovateBroker.placeOrder(symbol, qty, action);
  return paper.placeOrder(symbol, qty, action);
}

export async function closePosition(symbol: string): Promise<OrderResult> {
  if (process.env.PAPER_MODE === "true") return paper.closePosition(symbol);
  if (activeBroker === "tradovate") return tradovateBroker.closePosition(symbol);
  return paper.closePosition(symbol);
}

export async function getActiveStatus(): Promise<{ name: string; balance: number; positions: Position[] }> {
  const broker = activeBroker === "tradovate" ? tradovateBroker : paper;
  return {
    name: activeBroker,
    balance: await broker.getBalance(),
    positions: await broker.getPositions(),
  };
}
