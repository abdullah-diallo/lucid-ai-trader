-- ============================================================
-- Lucid AI Trader — Supabase Schema
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================

-- Enable UUID extension (already enabled on Supabase by default)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users (custom auth — username + bcrypt hash) ──────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT        UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    last_sign_in  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (lower(username));

-- ── Profiles ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    user_id      UUID    PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT,
    paper_mode   BOOLEAN DEFAULT TRUE,
    order_qty    INTEGER DEFAULT 1,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Trading Signals ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    symbol      TEXT        NOT NULL,
    action      TEXT        NOT NULL CHECK (action IN ('BUY','SELL','CLOSE')),
    price       NUMERIC(14, 4),
    timeframe   TEXT,
    reason      TEXT,
    source      TEXT        DEFAULT 'tradingview',
    signal_type TEXT,
    raw_payload JSONB,
    received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_user_id    ON signals (user_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol     ON signals (symbol);
CREATE INDEX IF NOT EXISTS idx_signals_received   ON signals (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_action     ON signals (action);

-- ── Trades (executed positions) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    signal_id       UUID        REFERENCES signals(id) ON DELETE SET NULL,
    symbol          TEXT        NOT NULL,
    direction       TEXT        NOT NULL CHECK (direction IN ('BUY','SELL')),
    entry_price     NUMERIC(14, 4),
    exit_price      NUMERIC(14, 4),
    quantity        INTEGER     DEFAULT 1,
    pnl             NUMERIC(14, 4),
    status          TEXT        DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
    paper_mode      BOOLEAN     DEFAULT TRUE,
    broker_order_id TEXT,
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_user_id  ON trades (user_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol   ON trades (symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status   ON trades (status);
CREATE INDEX IF NOT EXISTS idx_trades_opened   ON trades (opened_at DESC);

-- ── P&L Snapshots (daily rollup) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id            UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID    REFERENCES users(id) ON DELETE CASCADE,
    date          DATE    NOT NULL,
    gross_profit  NUMERIC(14, 4) DEFAULT 0,
    gross_loss    NUMERIC(14, 4) DEFAULT 0,
    net_pnl       NUMERIC(14, 4) DEFAULT 0,
    total_trades  INTEGER        DEFAULT 0,
    winners       INTEGER        DEFAULT 0,
    losers        INTEGER        DEFAULT 0,
    created_at    TIMESTAMPTZ    DEFAULT NOW(),
    UNIQUE (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_pnl_user_date ON pnl_snapshots (user_id, date DESC);

-- ── Strategy Configs (per-user enable/disable + overrides) ────────────────────
CREATE TABLE IF NOT EXISTS strategy_configs (
    id          UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID    REFERENCES users(id) ON DELETE CASCADE,
    strategy_id TEXT    NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    config      JSONB   DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, strategy_id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_configs_user ON strategy_configs (user_id);

-- ── TradingView Accounts ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tv_accounts (
    id           UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID    REFERENCES users(id) ON DELETE CASCADE,
    tv_username  TEXT    NOT NULL,
    display_name TEXT,
    symbol       TEXT    DEFAULT 'CME_MINI:MES1!',
    interval     TEXT    DEFAULT '5',
    theme        TEXT    DEFAULT 'dark',
    notes        TEXT,
    is_active    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tv_accounts_user ON tv_accounts (user_id);

-- ── TradingView Chart Config (one row per user) ───────────────────────────────
CREATE TABLE IF NOT EXISTS tv_config (
    user_id              UUID    PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    symbol               TEXT    DEFAULT 'CME_MINI:MES1!',
    interval             TEXT    DEFAULT '5',
    theme                TEXT    DEFAULT 'dark',
    style                TEXT    DEFAULT '1',
    studies              JSONB   DEFAULT '["RSI@tv-basicstudies","VWAP@tv-basicstudies"]',
    active_tv_account_id UUID    REFERENCES tv_accounts(id) ON DELETE SET NULL,
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ── Session Logs ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_logs (
    id            UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID    REFERENCES users(id) ON DELETE SET NULL,
    session_type  TEXT,
    signals_count INTEGER DEFAULT 0,
    trades_count  INTEGER DEFAULT 0,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    ended_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_session_logs_user ON session_logs (user_id);

-- ── ORB State Snapshots ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orb_snapshots (
    id            UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID    REFERENCES users(id) ON DELETE SET NULL,
    symbol        TEXT    NOT NULL,
    orb_high      NUMERIC(14, 4),
    orb_low       NUMERIC(14, 4),
    orb_range     NUMERIC(14, 4),
    long_target1  NUMERIC(14, 4),
    long_target2  NUMERIC(14, 4),
    long_target3  NUMERIC(14, 4),
    short_target1 NUMERIC(14, 4),
    short_target2 NUMERIC(14, 4),
    short_target3 NUMERIC(14, 4),
    established   BOOLEAN DEFAULT FALSE,
    signal_type   TEXT,
    captured_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orb_user_date ON orb_snapshots (user_id, captured_at DESC);

-- ── Disable RLS (server uses service_role key which bypasses RLS anyway) ──────
ALTER TABLE users            DISABLE ROW LEVEL SECURITY;
ALTER TABLE profiles         DISABLE ROW LEVEL SECURITY;
ALTER TABLE signals          DISABLE ROW LEVEL SECURITY;
ALTER TABLE trades           DISABLE ROW LEVEL SECURITY;
ALTER TABLE pnl_snapshots    DISABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_configs DISABLE ROW LEVEL SECURITY;
ALTER TABLE tv_accounts      DISABLE ROW LEVEL SECURITY;
ALTER TABLE tv_config        DISABLE ROW LEVEL SECURITY;
ALTER TABLE session_logs     DISABLE ROW LEVEL SECURITY;
ALTER TABLE orb_snapshots    DISABLE ROW LEVEL SECURITY;
