"""
dashboard/server.py
===================
Apple-style glassmorphic trading dashboard for lucid-ai-trader.
Runs on port 5050 — separate from the webhook receiver on port 8080.

Start: python dashboard/server.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

# ── Project root on sys.path so we can import core/ and analysis/ ──────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from broker.trade_executor import TradeExecutor
from broker.tradovate_client import TradovateClient
from core.session_manager import SessionManager
from data.tradingview_client import InMemoryEventBus, TradingViewWebhookReceiver

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")

# ── Shared event bus — wires webhook receiver → trade executor ───────────────
_event_bus = InMemoryEventBus()
TradingViewWebhookReceiver(app=app, event_bus=_event_bus)

_trade_executor: Optional[TradeExecutor] = None


def _init_trade_executor() -> None:
    global _trade_executor
    paper_mode = os.getenv("PAPER_MODE", "true").lower() == "true"
    order_qty = int(os.getenv("ORDER_QTY", "1"))
    client = TradovateClient(
        base_url=os.getenv("TRADOVATE_API_BASE_URL", "https://demo-api.tradovate.com"),
        username=os.getenv("TRADOVATE_USERNAME", ""),
        password=os.getenv("TRADOVATE_PASSWORD", ""),
        client_id=os.getenv("TRADOVATE_CLIENT_ID", ""),
        client_secret=os.getenv("TRADOVATE_CLIENT_SECRET", ""),
    )
    _trade_executor = TradeExecutor(client=client, paper_mode=paper_mode, order_qty=order_qty)
    try:
        _trade_executor.initialize()
        _trade_executor.attach(_event_bus)
    except Exception:
        logger.exception("TradeExecutor failed to initialise — running in degraded mode.")

# ── Module-level singletons ─────────────────────────────────────────────────
_session_manager: Optional[SessionManager] = None
_paused: bool = False

TV_CONFIG_PATH = ROOT / "data" / "tv_config.json"
TV_ACCOUNTS_PATH = ROOT / "data" / "tv_accounts.json"

DEFAULT_TV_CONFIG: Dict[str, Any] = {
    "symbol": "CME_MINI:MES1!",
    "interval": "5",
    "theme": "dark",
    "style": "1",
    "studies": ["RSI@tv-basicstudies", "VWAP@tv-basicstudies"],
    "active_account_id": None,
}


def _load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def get_db_path() -> str:
    return os.getenv("SQLITE_DB_PATH", str(ROOT / "data" / "lucid_trader.db"))


def db_connect() -> Optional[sqlite3.Connection]:
    path = get_db_path()
    if not Path(path).exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    sm = get_session_manager()
    now = datetime.now(sm.tz)
    session = sm.get_current_session()
    high_vol = sm.is_high_volume_time()
    news_win = sm.is_news_window()
    should_trade = (not _paused) and sm.should_trade_now()
    until_next = sm.time_until_next_session()
    paper_mode = os.getenv("PAPER_MODE", "true").lower() == "true"

    total_seconds = int(until_next.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    countdown = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return jsonify({
        "session": session,
        "should_trade": should_trade,
        "high_volume": high_vol,
        "news_window": news_win,
        "paused": _paused,
        "paper_mode": paper_mode,
        "time_et": now.strftime("%I:%M:%S %p ET"),
        "date_et": now.strftime("%A, %B %d %Y"),
        "countdown": countdown,
        "until_next_label": _next_boundary_label(session),
    })


@app.get("/api/signals")
def api_signals():
    limit = min(int(request.args.get("limit", 20)), 100)
    conn = db_connect()
    signals: List[Dict[str, Any]] = []

    if conn:
        try:
            cur = conn.execute(
                "SELECT * FROM signals ORDER BY received_at DESC LIMIT ?", (limit,)
            )
            signals = [dict(row) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return jsonify({"signals": signals, "count": len(signals)})


@app.get("/api/performance")
def api_performance():
    conn = db_connect()
    stats: Dict[str, Any] = {
        "total_signals": 0,
        "buy_signals": 0,
        "sell_signals": 0,
        "close_signals": 0,
        "filtered_signals": 0,
        "paper_trades": 0,
    }

    if conn:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cur = conn.execute(
                "SELECT action, COUNT(*) as cnt FROM signals WHERE received_at LIKE ? GROUP BY action",
                (f"{today}%",),
            )
            for row in cur.fetchall():
                action = (row["action"] or "").upper()
                count = row["cnt"]
                stats["total_signals"] += count
                if action == "BUY":
                    stats["buy_signals"] = count
                elif action == "SELL":
                    stats["sell_signals"] = count
                elif action == "CLOSE":
                    stats["close_signals"] = count
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return jsonify(stats)


@app.get("/api/pnl")
def api_pnl():
    """Calculate P&L from paired BUY/SELL → CLOSE signal sequences."""
    conn = db_connect()
    result: Dict[str, Any] = {
        "total_trades": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "win_rate": 0.0,
        "winners": 0,
        "losers": 0,
        "money_in": 0.0,
        "money_out": 0.0,
    }
    if not conn:
        return jsonify(result)

    try:
        rows = conn.execute(
            "SELECT action, price, symbol, received_at FROM signals "
            "WHERE price IS NOT NULL ORDER BY received_at ASC"
        ).fetchall()

        open_trades: Dict[str, Dict[str, Any]] = {}
        closed_pnls: List[float] = []

        for row in rows:
            action = (row["action"] or "").upper()
            price = row["price"]
            symbol = row["symbol"] or "UNKNOWN"

            if action in ("BUY", "SELL"):
                open_trades[symbol] = {"action": action, "price": float(price)}
            elif action == "CLOSE" and symbol in open_trades:
                entry = open_trades.pop(symbol)
                pnl = (
                    float(price) - entry["price"]
                    if entry["action"] == "BUY"
                    else entry["price"] - float(price)
                )
                closed_pnls.append(pnl)

        if closed_pnls:
            winners = [p for p in closed_pnls if p > 0]
            losers  = [p for p in closed_pnls if p <= 0]
            result.update({
                "total_trades": len(closed_pnls),
                "gross_profit": round(sum(winners), 2),
                "gross_loss":   round(sum(losers), 2),
                "net_pnl":      round(sum(closed_pnls), 2),
                "winners":      len(winners),
                "losers":       len(losers),
                "win_rate":     round(len(winners) / len(closed_pnls) * 100, 1),
                "money_in":     round(sum(winners), 2),
                "money_out":    round(abs(sum(losers)), 2),
            })
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return jsonify(result)


@app.post("/api/pause")
def api_pause():
    global _paused
    _paused = True
    logger.info("Dashboard: trading paused.")
    return jsonify({"paused": True})


@app.post("/api/resume")
def api_resume():
    global _paused
    _paused = False
    logger.info("Dashboard: trading resumed.")
    return jsonify({"paused": False})


# ── Strategies ───────────────────────────────────────────────────────────────

def _scan_strategies() -> List[Dict[str, Any]]:
    import ast as _ast
    analysis_dir = ROOT / "analysis"
    results = []

    # strategy_*.py first, then *_engine.py (excluding __init__)
    files: List[Path] = (
        sorted(analysis_dir.glob("strategy_*.py"))
        + sorted(p for p in analysis_dir.glob("*_engine.py") if not p.stem.startswith("__"))
    )

    for py_file in files:
        stem = py_file.stem
        display_name = (
            stem.replace("strategy_", "")
                .replace("_engine", " Engine")
                .replace("_", " ")
                .title()
        )
        description = ""
        class_name = ""
        methods_count = 0
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = _ast.parse(source)
            description = (_ast.get_docstring(tree) or "").split("\n")[0].strip()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ClassDef):
                    if not class_name:
                        class_name = node.name
                    methods_count += sum(
                        1 for item in node.body
                        if isinstance(item, _ast.FunctionDef)
                        and not item.name.startswith("_")
                    )
        except Exception:
            pass
        results.append({
            "id": stem,
            "display_name": display_name,
            "file": py_file.name,
            "class_name": class_name,
            "description": description,
            "methods_count": methods_count,
            "enabled": True,
        })
    return results


@app.get("/api/strategies")
def api_strategies():
    strategies = _scan_strategies()
    return jsonify({"strategies": strategies, "count": len(strategies)})


@app.get("/api/strategies/<strategy_id>")
def api_strategy_detail(strategy_id: str):
    import ast as _ast
    analysis_dir = ROOT / "analysis"

    candidates = list(analysis_dir.glob(f"{strategy_id}.py"))
    if not candidates:
        candidates = list(analysis_dir.glob(f"strategy_{strategy_id}.py"))
    if not candidates:
        return jsonify({"error": "Strategy not found"}), 404

    py_file = candidates[0]
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = _ast.parse(source)
        module_doc = _ast.get_docstring(tree) or ""
        classes = []

        for node in _ast.walk(tree):
            if not isinstance(node, _ast.ClassDef):
                continue
            class_doc = _ast.get_docstring(node) or ""
            methods = []
            init_params: List[str] = []

            for item in node.body:
                if not isinstance(item, _ast.FunctionDef):
                    continue
                if item.name.startswith("_") and item.name != "__init__":
                    continue
                m_doc = _ast.get_docstring(item) or ""
                params = [a.arg for a in item.args.args if a.arg != "self"]
                if item.name == "__init__":
                    init_params = params
                else:
                    methods.append({"name": item.name, "doc": m_doc, "params": params})

            classes.append({
                "name": node.name,
                "doc": class_doc,
                "init_params": init_params,
                "methods": methods,
            })

        return jsonify({
            "id": py_file.stem,
            "file": py_file.name,
            "module_doc": module_doc,
            "classes": classes,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── TradingView config & accounts ────────────────────────────────────────────

@app.get("/api/tradingview/config")
def api_tv_config_get():
    config = _load_json(TV_CONFIG_PATH, DEFAULT_TV_CONFIG.copy())
    return jsonify(config)


@app.post("/api/tradingview/config")
def api_tv_config_update():
    data = request.get_json(force=True, silent=True) or {}
    config = _load_json(TV_CONFIG_PATH, DEFAULT_TV_CONFIG.copy())
    allowed = {"symbol", "interval", "theme", "style", "studies"}
    for k, v in data.items():
        if k in allowed:
            config[k] = v
    _save_json(TV_CONFIG_PATH, config)
    return jsonify(config)


@app.get("/api/tradingview/accounts")
def api_tv_accounts_list():
    accounts = _load_json(TV_ACCOUNTS_PATH, [])
    config = _load_json(TV_CONFIG_PATH, DEFAULT_TV_CONFIG.copy())
    return jsonify({
        "accounts": accounts,
        "active_account_id": config.get("active_account_id"),
    })


@app.post("/api/tradingview/accounts")
def api_tv_accounts_create():
    data = request.get_json(force=True, silent=True) or {}
    accounts: List[Dict[str, Any]] = _load_json(TV_ACCOUNTS_PATH, [])
    account: Dict[str, Any] = {
        "id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "username":     data.get("username", "").strip(),
        "display_name": data.get("display_name", data.get("username", "Account")).strip(),
        "symbol":       data.get("symbol", "CME_MINI:MES1!"),
        "interval":     data.get("interval", "5"),
        "theme":        data.get("theme", "dark"),
        "notes":        data.get("notes", ""),
    }
    accounts.append(account)
    _save_json(TV_ACCOUNTS_PATH, accounts)
    return jsonify(account), 201


@app.post("/api/tradingview/accounts/<account_id>/activate")
def api_tv_account_activate(account_id: str):
    accounts: List[Dict[str, Any]] = _load_json(TV_ACCOUNTS_PATH, [])
    account = next((a for a in accounts if a["id"] == account_id), None)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    config = _load_json(TV_CONFIG_PATH, DEFAULT_TV_CONFIG.copy())
    config.update({
        "active_account_id": account_id,
        "symbol":   account.get("symbol", config["symbol"]),
        "interval": account.get("interval", config["interval"]),
        "theme":    account.get("theme", config["theme"]),
    })
    _save_json(TV_CONFIG_PATH, config)
    return jsonify(config)


@app.delete("/api/tradingview/accounts/<account_id>")
def api_tv_account_delete(account_id: str):
    accounts: List[Dict[str, Any]] = _load_json(TV_ACCOUNTS_PATH, [])
    accounts = [a for a in accounts if a["id"] != account_id]
    _save_json(TV_ACCOUNTS_PATH, accounts)
    config = _load_json(TV_CONFIG_PATH, DEFAULT_TV_CONFIG.copy())
    if config.get("active_account_id") == account_id:
        config["active_account_id"] = accounts[0]["id"] if accounts else None
        _save_json(TV_CONFIG_PATH, config)
    return jsonify({"ok": True})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _next_boundary_label(session: str) -> str:
    labels = {
        "Globex": "Pre-market open",
        "Pre-market": "RTH open",
        "RTH": "Market close",
        "AH": "Globex open",
        "Closed": "Next session",
    }
    return labels.get(session, "Next session")


# ── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _init_trade_executor()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    logger.info("Lucid AI Trader dashboard starting on http://localhost:%s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
