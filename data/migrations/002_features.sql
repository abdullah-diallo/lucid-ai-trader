-- 002_features.sql
-- Run in Supabase SQL Editor.
-- All statements use IF NOT EXISTS / IF NOT EXISTS guards — safe to re-run.

-- ── 1. Accounts table ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    account_type        TEXT NOT NULL CHECK (account_type IN ('PROP_FIRM','PERSONAL_LIVE','DEMO','MANUAL')),
    risk_mode           TEXT NOT NULL DEFAULT 'BALANCED' CHECK (risk_mode IN ('PROTECTED','BALANCED','FREE','SIMULATION')),
    trading_mode        TEXT NOT NULL DEFAULT 'SEMI_AUTO' CHECK (trading_mode IN ('FULL_AUTO','SEMI_AUTO','SIGNALS_ONLY')),
    starting_balance    NUMERIC(14,2) DEFAULT 0,
    current_balance     NUMERIC(14,2) DEFAULT 0,
    daily_pnl           NUMERIC(14,2) DEFAULT 0,
    total_pnl           NUMERIC(14,2) DEFAULT 0,
    daily_loss_limit    NUMERIC(14,2) DEFAULT 0,
    max_drawdown_pct    NUMERIC(5,2)  DEFAULT 5.0,
    max_contracts       INTEGER       DEFAULT 1,
    is_active           BOOLEAN       DEFAULT FALSE,
    broker              TEXT          DEFAULT 'tradovate',
    is_evaluation_phase BOOLEAN       DEFAULT FALSE,
    notes               TEXT,
    autonomous_mode     BOOLEAN       DEFAULT FALSE,
    created_at          TIMESTAMPTZ   DEFAULT NOW(),
    last_updated        TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts (user_id);
ALTER TABLE accounts DISABLE ROW LEVEL SECURITY;

-- ── 2. Extend signals table (additive — existing rows unaffected) ──────────────
ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS strategy_name TEXT,
    ADD COLUMN IF NOT EXISTS stop_loss     NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS target_1      NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS target_2      NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS target_3      NUMERIC(14,4),
    ADD COLUMN IF NOT EXISTS confidence    NUMERIC(5,4);

CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals (strategy_name);

-- ── 3. Extend trades table ────────────────────────────────────────────────────
ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy_name TEXT;
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy_name);

-- ── 4. Improvement history ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS improvement_history (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_name  TEXT NOT NULL,
    proposal_json  JSONB NOT NULL,
    applied_at     TIMESTAMPTZ DEFAULT NOW(),
    was_successful BOOLEAN,
    reverted_at    TIMESTAMPTZ
);

ALTER TABLE improvement_history DISABLE ROW LEVEL SECURITY;

-- ── 5. Autonomous action log ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS autonomous_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    type        TEXT NOT NULL,
    strategy    TEXT,
    signal_json JSONB,
    reasoning   TEXT,
    outcome     TEXT
);

ALTER TABLE autonomous_log DISABLE ROW LEVEL SECURITY;
