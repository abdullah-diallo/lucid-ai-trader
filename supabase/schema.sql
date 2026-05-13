-- ============================================================
-- Lucid AI Trader — Supabase Schema
-- Run this entire file in the Supabase SQL editor:
--   Dashboard → SQL Editor → New query → paste → Run
-- ============================================================

-- ── Extensions ────────────────────────────────────────────────────────────────
create extension if not exists "pgcrypto";

-- ── Users ─────────────────────────────────────────────────────────────────────
create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  username      text not null,
  password_hash text not null,
  created_at    timestamptz default now(),
  last_sign_in  timestamptz
);

-- Case-insensitive unique usernames
create unique index if not exists users_username_lower_idx
  on users (lower(username));

-- ── Profiles ──────────────────────────────────────────────────────────────────
create table if not exists profiles (
  user_id      uuid primary key references users(id) on delete cascade,
  display_name text,
  avatar_url   text,
  bio          text,
  timezone     text default 'America/New_York',
  updated_at   timestamptz default now()
);

-- ── Trading signals ───────────────────────────────────────────────────────────
create table if not exists signals (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references users(id) on delete cascade,
  symbol      text,
  action      text,           -- BUY | SELL | CLOSE
  price       numeric,
  timeframe   text,
  reason      text,
  source      text default 'tradingview',
  raw_payload jsonb,
  received_at timestamptz default now()
);

create index if not exists signals_user_received_idx
  on signals (user_id, received_at desc);

-- ── Executed trades ───────────────────────────────────────────────────────────
create table if not exists trades (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references users(id) on delete cascade,
  symbol      text,
  action      text,
  entry_price numeric,
  exit_price  numeric,
  qty         integer default 1,
  pnl         numeric,
  status      text default 'open',    -- open | closed | cancelled
  opened_at   timestamptz default now(),
  closed_at   timestamptz
);

create index if not exists trades_user_status_idx
  on trades (user_id, status);

-- ── Per-user strategy settings ────────────────────────────────────────────────
create table if not exists strategy_configs (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references users(id) on delete cascade,
  strategy_id text not null,
  enabled     boolean default true,
  config_json jsonb,
  updated_at  timestamptz default now(),
  unique (user_id, strategy_id)
);

-- ── TradingView chart config per user ─────────────────────────────────────────
create table if not exists tv_config (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid unique references users(id) on delete cascade,
  symbol               text default 'CME_MINI:MES1!',
  interval             text default '5',
  theme                text default 'dark',
  style                text default '1',
  studies              jsonb default '["RSI@tv-basicstudies","VWAP@tv-basicstudies"]',
  active_tv_account_id uuid,
  updated_at           timestamptz default now()
);

-- ── TradingView saved accounts ────────────────────────────────────────────────
create table if not exists tv_accounts (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid references users(id) on delete cascade,
  tv_username  text,
  display_name text,
  symbol       text default 'CME_MINI:MES1!',
  interval     text default '5',
  theme        text default 'dark',
  notes        text,
  is_active    boolean default false,
  created_at   timestamptz default now()
);

-- ── AI chat sessions ──────────────────────────────────────────────────────────
create table if not exists chat_sessions (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references users(id) on delete cascade,
  title      text default 'New Chat',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists chat_sessions_user_updated_idx
  on chat_sessions (user_id, updated_at desc);

-- ── AI chat messages ──────────────────────────────────────────────────────────
create table if not exists chat_messages (
  id         uuid primary key default gen_random_uuid(),
  session_id uuid references chat_sessions(id) on delete cascade,
  user_id    uuid references users(id) on delete cascade,
  role       text check (role in ('user', 'assistant', 'system')) not null,
  content    text not null,
  created_at timestamptz default now()
);

create index if not exists chat_messages_session_created_idx
  on chat_messages (session_id, created_at);
