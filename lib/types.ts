// ── Trading Signal ─────────────────────────────────────────────────────────────
export type SignalAction = "BUY" | "SELL" | "CLOSE";
export type SignalStatus = "pending" | "approved" | "rejected" | "executed" | "filtered";

export interface TradingSignal {
  symbol: string;
  action: SignalAction;
  price: number;
  timeframe: string;
  reason: string;
  strategy?: string;
  confidence?: number;
}

// ── Strategy Result ────────────────────────────────────────────────────────────
export interface SignalResult {
  setupType: string;
  direction: "BULLISH" | "BEARISH" | null;
  confidence: number;
  reason: string;
  entryPrice: number;
  stopPrice: number;
  target1: number;
  target2: number;
  metadata?: Record<string, unknown>;
}

// ── OHLCV Candle ───────────────────────────────────────────────────────────────
export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// ── Market Session ─────────────────────────────────────────────────────────────
export type MarketSession = "RTH" | "Pre-market" | "AH" | "Globex" | "Closed";

// ── Trading Mode ───────────────────────────────────────────────────────────────
export type TradingMode = "FULL_AUTO" | "SEMI_AUTO" | "SIGNALS_ONLY";

// ── Risk Mode ──────────────────────────────────────────────────────────────────
export type RiskMode = "PROTECTED" | "BALANCED" | "FREE" | "SIMULATION";

// ── Account Type ───────────────────────────────────────────────────────────────
export type AccountType = "PROP_FIRM" | "PERSONAL_LIVE" | "DEMO" | "MANUAL";

// ── Risk Check Result ──────────────────────────────────────────────────────────
export interface RiskCheckResult {
  allowed: boolean;
  haltLevel: 0 | 1 | 2 | 3 | 4 | 5;
  reason: string;
  confidenceThreshold: number;
  maxContracts: number;
  allowedStrategies: string[] | null;
  telegramMessage: string;
}

// ── Account ────────────────────────────────────────────────────────────────────
export interface Account {
  _id: string;
  userId: string;
  name: string;
  accountType: AccountType;
  riskMode: RiskMode;
  tradingMode: TradingMode;
  startingBalance: number;
  currentBalance: number;
  dailyPnl: number;
  totalPnl: number;
  dailyLossLimit: number;
  maxDrawdownPct: number;
  maxContracts: number;
  broker: "paper" | "tradovate" | "ibkr";
  isActive: boolean;
  autonomousMode: boolean;
}

// ── Broker ─────────────────────────────────────────────────────────────────────
export interface OrderResult {
  ok: boolean;
  orderId?: string;
  message: string;
  filledPrice?: number;
  qty?: number;
}

export interface Position {
  symbol: string;
  qty: number;
  side: "Long" | "Short";
  entryPrice: number;
  currentPnl: number;
}

export interface BrokerStatus {
  name: string;
  connected: boolean;
  balance?: number;
  positions?: Position[];
  connectionFields: ConnectionField[];
}

export interface ConnectionField {
  key: string;
  label: string;
  type: "text" | "password";
  required: boolean;
}

// ── P&L Stats ──────────────────────────────────────────────────────────────────
export interface PnlStats {
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  grossProfit: number;
  grossLoss: number;
  netPnl: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  sharpe: number;
}

// ── Backtest ───────────────────────────────────────────────────────────────────
export interface BacktestTrade {
  entryPrice: number;
  exitPrice: number;
  side: "Long" | "Short";
  qty: number;
  pnl: number;
  entryBar: number;
  exitBar: number;
  strategy: string;
}

export interface BacktestResult {
  strategy: string;
  symbol: string;
  start: string;
  end: string;
  trades: BacktestTrade[];
  equityCurve: number[];
  metrics: PnlStats & {
    sortino: number;
    maxDrawdown: number;
    consecutiveWins: number;
    consecutiveLosses: number;
  };
}
