import type { Account, RiskCheckResult, TradingSignal } from "./types";

// Protected strategies: only these are allowed for PROTECTED risk mode
const PROTECTED_STRATEGIES = ["ORB", "SMC", "BOS"];

// Daily trade caps by session (total cap: 6)
const SESSION_CAPS = {
  PRE_MARKET: 2,
  NY_OPEN: 3,    // 09:30–11:30
  NY_PM: 1,      // 14:00–16:00
};

export function checkTradeAllowed(
  account: Account,
  signal: TradingSignal,
  dailyTradeCount: number,
  peakBalance?: number
): RiskCheckResult {
  const ok = (overrides?: Partial<RiskCheckResult>): RiskCheckResult => ({
    allowed: true,
    haltLevel: 0,
    reason: "Trade allowed",
    confidenceThreshold: 0.5,
    maxContracts: account.maxContracts,
    allowedStrategies: null,
    telegramMessage: "",
    ...overrides,
  });

  const halt = (
    level: RiskCheckResult["haltLevel"],
    reason: string,
    msg?: string
  ): RiskCheckResult => ({
    allowed: false,
    haltLevel: level,
    reason,
    confidenceThreshold: 1,
    maxContracts: 0,
    allowedStrategies: null,
    telegramMessage: msg ?? `⛔ HALT L${level}: ${reason}`,
  });

  // 1. Daily trade cap
  if (dailyTradeCount >= 6) {
    return halt(2, "Daily trade cap reached (6 trades)");
  }

  // 2. Daily loss limit
  if (account.dailyPnl <= -account.dailyLossLimit) {
    return halt(4, `Daily loss limit hit: $${account.dailyPnl.toFixed(2)}`);
  }

  // 3. Drawdown check
  const peak = peakBalance ?? account.startingBalance;
  const drawdown = peak > 0 ? (peak - account.currentBalance) / peak : 0;
  if (drawdown >= account.maxDrawdownPct / 100) {
    return halt(5, `Max drawdown reached: ${(drawdown * 100).toFixed(1)}%`);
  }

  // 4. Risk mode gates
  const strategy = signal.strategy?.toUpperCase();

  if (account.riskMode === "PROTECTED") {
    if (strategy && !PROTECTED_STRATEGIES.includes(strategy)) {
      return halt(1, `Strategy ${strategy} not allowed in PROTECTED mode`, "");
    }
    return ok({
      allowedStrategies: PROTECTED_STRATEGIES,
      confidenceThreshold: 0.7,
      maxContracts: 1,
    });
  }

  if (account.riskMode === "BALANCED") {
    const confidence = signal.confidence ?? 0;
    if (confidence < 0.65) {
      return halt(1, `Confidence too low: ${confidence} < 0.65`);
    }
    return ok({ confidenceThreshold: 0.65, maxContracts: Math.min(account.maxContracts, 2) });
  }

  if (account.riskMode === "FREE") {
    const confidence = signal.confidence ?? 0;
    let contracts = 1;
    if (confidence >= 0.85) contracts = 3;
    else if (confidence >= 0.75) contracts = 2;
    else if (confidence >= 0.65) contracts = 1;
    else return halt(1, `Confidence too low: ${confidence} < 0.65`);
    return ok({ maxContracts: Math.min(contracts, account.maxContracts) });
  }

  // SIMULATION — always allowed
  return ok({ maxContracts: 1, confidenceThreshold: 0 });
}
