"""
journal/trade_logger.py
========================
Local SQLite trade journal with safe schema migrations.
Acts as a write-ahead cache for trades that also sync to Supabase.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_DB_PATH = os.environ.get("TRADE_JOURNAL_DB", "trade_journal.db")

_NEW_COLUMNS = [
    ("account_id",              "INTEGER"),
    ("strategy_code",           "TEXT"),
    ("strategy_full_name",      "TEXT"),
    ("confidence",              "REAL"),
    ("confluence_factors",      "TEXT"),       # JSON string
    ("probability_pct",         "INTEGER"),
    ("session",                 "TEXT"),
    ("kill_zone",               "INTEGER"),    # 0 or 1
    ("htf_bias",                "TEXT"),
    ("vwap_position",           "TEXT"),
    ("entry_type",              "TEXT"),
    ("exit_reason",             "TEXT"),
    ("max_adverse_excursion",   "REAL"),
    ("max_favorable_excursion", "REAL"),
    ("bars_held",               "INTEGER"),
    ("mode",                    "TEXT"),       # FULL_AUTO / SEMI_AUTO / SIGNALS_ONLY
    ("manually_taken",          "INTEGER DEFAULT 0"),
]

_BASE_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT,
    strategy_name   TEXT,
    symbol          TEXT,
    direction       TEXT,
    qty             INTEGER,
    entry_price     REAL,
    exit_price      REAL,
    pnl             REAL,
    status          TEXT DEFAULT 'open',
    opened_at       TEXT,
    closed_at       TEXT,
    notes           TEXT
)
"""


class TradeLogger:
    """Local SQLite trade journal with safe schema migrations."""

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self.engine: Engine = create_engine(f"sqlite:///{db_path}", future=True)
        self._ensure_base_table()

    # ── Schema management ──────────────────────────────────────────────────────

    def _ensure_base_table(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text(_BASE_DDL))
            conn.commit()

    def run_migration(self) -> None:
        """Add new columns to the trades table safely (skips existing columns)."""
        with self.engine.connect() as conn:
            existing = conn.execute(text("PRAGMA table_info(trades)")).fetchall()
            existing_names = {row[1] for row in existing}
            for col_name, col_type in _NEW_COLUMNS:
                bare_name = col_name.split()[0]
                if bare_name not in existing_names:
                    conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}"))
                    logger.info("Migration: added column %s", col_name)
            conn.commit()

    def verify_schema(self) -> bool:
        """Confirm every expected column is present. Raises AssertionError on failure."""
        with self.engine.connect() as conn:
            existing = conn.execute(text("PRAGMA table_info(trades)")).fetchall()
        existing_names = {row[1] for row in existing}
        missing = []
        for col_name, _ in _NEW_COLUMNS:
            bare_name = col_name.split()[0]
            if bare_name not in existing_names:
                missing.append(bare_name)
        if missing:
            raise AssertionError(f"Missing columns in trades table: {missing}")
        logger.info("Schema verified — all %d migration columns present.", len(_NEW_COLUMNS))
        return True

    # ── Write ──────────────────────────────────────────────────────────────────

    def log_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        """
        Insert a trade dict into the local journal.
        Returns the new row id, or None on failure.
        """
        if "confluence_factors" in trade and isinstance(trade["confluence_factors"], (list, dict)):
            trade = dict(trade)
            trade["confluence_factors"] = json.dumps(trade["confluence_factors"])

        cols = ", ".join(trade.keys())
        placeholders = ", ".join(f":{k}" for k in trade.keys())
        sql = text(f"INSERT INTO trades ({cols}) VALUES ({placeholders})")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(sql, trade)
                conn.commit()
                return result.lastrowid
        except Exception:
            logger.exception("Failed to log trade: %s", trade)
            return None

    def update_trade(self, trade_id: int, updates: Dict[str, Any]) -> bool:
        """Patch an existing trade row by id."""
        if "confluence_factors" in updates and isinstance(updates["confluence_factors"], (list, dict)):
            updates = dict(updates)
            updates["confluence_factors"] = json.dumps(updates["confluence_factors"])

        set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
        sql = text(f"UPDATE trades SET {set_clause} WHERE id = :_id")
        try:
            with self.engine.connect() as conn:
                conn.execute(sql, {**updates, "_id": trade_id})
                conn.commit()
            return True
        except Exception:
            logger.exception("Failed to update trade %d.", trade_id)
            return False

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_trades(
        self,
        user_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Query trades with optional filters."""
        filters, params = [], {}
        if user_id:
            filters.append("user_id = :user_id")
            params["user_id"] = user_id
        if strategy_name:
            filters.append("strategy_name = :strategy_name")
            params["strategy_name"] = strategy_name
        if status:
            filters.append("status = :status")
            params["status"] = status

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = text(f"SELECT * FROM trades {where} ORDER BY opened_at DESC LIMIT :limit")
        params["limit"] = limit

        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, params).mappings().fetchall()
            trades = [dict(r) for r in rows]
            for t in trades:
                if t.get("confluence_factors"):
                    try:
                        t["confluence_factors"] = json.loads(t["confluence_factors"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return trades
        except Exception:
            logger.exception("Failed to query trades.")
            return []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
