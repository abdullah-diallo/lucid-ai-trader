"""
dashboard/server.py — Lucid AI Trader
======================================
Flask dashboard with:
  - Supabase backend (all data)
  - Session-based auth (/signup, /login, /logout)
  - TradingView webhook receiver
  - Groq AI analysis endpoint
  - Full REST API for dashboard polling
"""
from __future__ import annotations

import ast as _ast
import functools
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_socketio import SocketIO

load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from accounts.account_manager import AccountManager
from ai.high_conviction import HighConvictionChecker
from alerts.telegram_bot import TelegramBot
from broker.trade_executor import TradeExecutor
from broker.broker_registry import broker_registry
from core.performance_engine import StrategyPerformanceEngine
from core.self_improvement_engine import SelfImprovementEngine
from core.session_manager import SessionManager
from core.state_manager import StateManager
from api.routes_tradingview import tv_bp
from core.drawing_queue import drawing_queue
from data.auth import authenticate_user
from data.supabase_client import get_supabase
from data.tradingview_client import InMemoryEventBus, TradingViewWebhookReceiver
from risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "lucid-dev-secret-change-me")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
app.register_blueprint(tv_bp)

_event_bus = InMemoryEventBus()
TradingViewWebhookReceiver(app=app, event_bus=_event_bus)

_trade_executor:      Optional[TradeExecutor]              = None
_session_manager:     Optional[SessionManager]             = None
_account_manager:     Optional[AccountManager]             = None
_risk_manager:        Optional[RiskManager]                = None
_state_manager:       Optional[StateManager]               = None
_performance_engine:  Optional[StrategyPerformanceEngine]  = None
_self_improvement:    Optional[SelfImprovementEngine]      = None
_telegram_bot:        Optional[TelegramBot]                = None
_paused: bool = False

def emit_socket_event(event: str, data: Any) -> None:
    """Thread-safe SocketIO emit. Call from trading loop or API handlers."""
    try:
        socketio.emit(event, data)
    except Exception:
        logger.debug("SocketIO emit failed for event %s", event)


TV_CONFIG_DEFAULTS: Dict[str, Any] = {
    "symbol":   "AMEX:SPY",
    "interval": "5",
    "theme":    "dark",
    "style":    "1",
    "studies":  ["RSI@tv-basicstudies", "VWAP@tv-basicstudies"],
    "active_account_id": None,
}


# ── Auth helpers ──────────────────────────────────────────────────────────────

def current_user_id() -> Optional[str]:
    return session.get("user_id")


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


# ── Singletons ────────────────────────────────────────────────────────────────

def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def get_account_manager() -> AccountManager:
    global _account_manager
    if _account_manager is None:
        _account_manager = AccountManager()
    return _account_manager


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager(get_account_manager(), get_risk_manager())
    return _state_manager


def get_performance_engine() -> StrategyPerformanceEngine:
    global _performance_engine
    if _performance_engine is None:
        _performance_engine = StrategyPerformanceEngine()
    return _performance_engine


def get_telegram_bot() -> Optional[TelegramBot]:
    return _telegram_bot


def _init_systems() -> None:
    """Initialize all subsystems and wire dependencies."""
    global _trade_executor, _telegram_bot, _self_improvement

    # ── Trade executor (now broker-agnostic) ──────────────────────────────────
    paper_mode = os.getenv("PAPER_MODE", "true").lower() == "true"
    order_qty  = int(os.getenv("ORDER_QTY", "1"))
    _trade_executor = TradeExecutor(paper_mode=paper_mode, order_qty=order_qty)
    try:
        _trade_executor.initialize()
    except Exception:
        logger.exception("TradeExecutor init failed — degraded mode.")

    # ── State manager wired to event bus (replaces executor.attach) ───────────
    sm = get_state_manager()
    sm.set_trade_executor(_trade_executor)
    hc = HighConvictionChecker(get_risk_manager())
    sm.set_high_conviction_checker(hc)
    sm.attach_to_event_bus(_event_bus)

    # ── Telegram bot ──────────────────────────────────────────────────────────
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if telegram_token:
        _telegram_bot = TelegramBot()
        _telegram_bot.set_state_manager(sm)
        _telegram_bot.set_performance_engine(get_performance_engine())
        _telegram_bot.set_account_manager(get_account_manager())
        _telegram_bot.set_risk_manager(get_risk_manager())
        sm.set_telegram_bot(_telegram_bot)

        # ── Self-improvement engine ───────────────────────────────────────────
        _self_improvement = SelfImprovementEngine(get_performance_engine())
        _self_improvement.set_telegram_bot(_telegram_bot)
        _telegram_bot.set_self_improvement_engine(_self_improvement)
        _self_improvement.start_scheduler()

        _telegram_bot.start()
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram features disabled.")


# Keep old name as alias for any direct calls
def _init_trade_executor() -> None:
    _init_systems()


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.get("/signup")
@app.post("/signup")
def signup_disabled():
    return redirect(url_for("login_page"))


@app.get("/login")
def login_page():
    if current_user_id():
        return redirect("/#tradingview")
    message = request.args.get("message", "")
    return render_template("login.html", message=message)


@app.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    try:
        user = authenticate_user(username, password)
    except Exception as exc:
        logger.exception("Login error")
        return render_template("login.html", error=f"Server error: {exc}", username=username)

    if not user:
        return render_template("login.html", error="Invalid ID or password.", username=username)

    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    next_url = request.form.get("next") or request.args.get("next") or "/#tradingview"
    return redirect(next_url)


@app.post("/logout")
@require_auth
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/")
@require_auth
def index():
    return render_template("index.html", username=session.get("username", ""))


# ── API: Status ───────────────────────────────────────────────────────────────

@app.get("/api/status")
@require_auth
def api_status():
    sm   = get_session_manager()
    now  = datetime.now(sm.tz)
    session_name = sm.get_current_session()
    until_next   = sm.time_until_next_session()
    paper_mode   = os.getenv("PAPER_MODE", "true").lower() == "true"

    total_sec = int(until_next.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s   = divmod(rem, 60)

    return jsonify({
        "session":          session_name,
        "should_trade":     (not _paused) and sm.should_trade_now(),
        "high_volume":      sm.is_high_volume_time(),
        "news_window":      sm.is_news_window(),
        "paused":           _paused,
        "paper_mode":       paper_mode,
        "time_et":          now.strftime("%I:%M:%S %p ET"),
        "date_et":          now.strftime("%A, %B %d %Y"),
        "countdown":        f"{h:02d}:{m:02d}:{s:02d}",
        "until_next_label": _next_boundary_label(session_name),
        "username":         session.get("username", ""),
    })


# ── API: Signals ──────────────────────────────────────────────────────────────

@app.get("/api/signals")
@require_auth
def api_signals():
    limit = min(int(request.args.get("limit", 20)), 100)
    uid   = current_user_id()
    try:
        sb  = get_supabase()
        res = (sb.table("signals")
                 .select("*")
                 .eq("user_id", uid)
                 .order("received_at", desc=True)
                 .limit(limit)
                 .execute())
        signals = res.data or []
    except Exception as exc:
        logger.warning("signals query failed: %s", exc)
        signals = []
    return jsonify({"signals": signals, "count": len(signals)})


# ── API: Performance ──────────────────────────────────────────────────────────

@app.get("/api/performance")
@require_auth
def api_performance():
    uid   = current_user_id()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats: Dict[str, Any] = {
        "total_signals": 0, "buy_signals": 0,
        "sell_signals": 0,  "close_signals": 0,
        "filtered_signals": 0,
    }
    try:
        sb  = get_supabase()
        res = (sb.table("signals")
                 .select("action")
                 .eq("user_id", uid)
                 .gte("received_at", today)
                 .execute())
        for row in (res.data or []):
            action = (row.get("action") or "").upper()
            stats["total_signals"] += 1
            if action == "BUY":   stats["buy_signals"]   += 1
            elif action == "SELL":  stats["sell_signals"]  += 1
            elif action == "CLOSE": stats["close_signals"] += 1
    except Exception as exc:
        logger.warning("performance query failed: %s", exc)
    return jsonify(stats)


# ── API: P&L ─────────────────────────────────────────────────────────────────

@app.get("/api/pnl")
@require_auth
def api_pnl():
    uid = current_user_id()
    result: Dict[str, Any] = {
        "total_trades": 0, "gross_profit": 0.0, "gross_loss": 0.0,
        "net_pnl": 0.0, "win_rate": 0.0, "winners": 0, "losers": 0,
        "money_in": 0.0, "money_out": 0.0,
    }
    try:
        sb  = get_supabase()
        res = (sb.table("trades")
                 .select("pnl, status")
                 .eq("user_id", uid)
                 .eq("status", "closed")
                 .execute())
        closed = res.data or []
        if closed:
            pnls    = [float(t["pnl"] or 0) for t in closed]
            winners = [p for p in pnls if p > 0]
            losers  = [p for p in pnls if p <= 0]
            result.update({
                "total_trades": len(pnls),
                "gross_profit": round(sum(winners), 2),
                "gross_loss":   round(sum(losers),  2),
                "net_pnl":      round(sum(pnls),    2),
                "winners":      len(winners),
                "losers":       len(losers),
                "win_rate":     round(len(winners) / len(pnls) * 100, 1) if pnls else 0.0,
                "money_in":     round(sum(winners), 2),
                "money_out":    round(abs(sum(losers)), 2),
            })
    except Exception as exc:
        logger.warning("pnl query failed: %s", exc)
        # Fallback: derive from signals
        result = _pnl_from_signals(uid)
    return jsonify(result)


def _pnl_from_signals(uid: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "total_trades": 0, "gross_profit": 0.0, "gross_loss": 0.0,
        "net_pnl": 0.0, "win_rate": 0.0, "winners": 0, "losers": 0,
        "money_in": 0.0, "money_out": 0.0,
    }
    try:
        sb  = get_supabase()
        res = (sb.table("signals")
                 .select("action, price, symbol")
                 .eq("user_id", uid)
                 .order("received_at")
                 .execute())
        open_trades: Dict[str, Dict] = {}
        pnls: List[float] = []
        for row in (res.data or []):
            action = (row.get("action") or "").upper()
            price  = row.get("price")
            sym    = row.get("symbol") or "UNK"
            if price is None:
                continue
            if action in ("BUY", "SELL"):
                open_trades[sym] = {"action": action, "price": float(price)}
            elif action == "CLOSE" and sym in open_trades:
                entry = open_trades.pop(sym)
                pnl = (float(price) - entry["price"]) if entry["action"] == "BUY" else (entry["price"] - float(price))
                pnls.append(pnl)
        if pnls:
            winners = [p for p in pnls if p > 0]
            losers  = [p for p in pnls if p <= 0]
            result.update({
                "total_trades": len(pnls),
                "gross_profit": round(sum(winners), 2),
                "gross_loss":   round(sum(losers),  2),
                "net_pnl":      round(sum(pnls),    2),
                "winners":      len(winners),
                "losers":       len(losers),
                "win_rate":     round(len(winners) / len(pnls) * 100, 1),
                "money_in":     round(sum(winners), 2),
                "money_out":    round(abs(sum(losers)), 2),
            })
    except Exception as exc:
        logger.warning("pnl fallback failed: %s", exc)
    return result


# ── API: Pause / Resume ───────────────────────────────────────────────────────

@app.post("/api/pause")
@require_auth
def api_pause():
    global _paused
    _paused = True
    emit_socket_event("halt_status", {"halted": True})
    return jsonify({"paused": True})


@app.post("/api/resume")
@require_auth
def api_resume():
    global _paused
    _paused = False
    emit_socket_event("halt_status", {"halted": False})
    return jsonify({"paused": False})


# ── API: Manual Trade ────────────────────────────────────────────────────────

@app.post("/api/trade/manual")
@require_auth
def api_trade_manual():
    global _paused
    if _paused:
        return jsonify({"error": "Trading is paused — resume first."}), 400

    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").upper().strip()
    symbol = (data.get("symbol") or "MES1!").strip()
    reason = (data.get("reason") or f"Manual {action} via dashboard").strip()

    if action not in {"BUY", "SELL", "CLOSE"}:
        return jsonify({"error": "action must be BUY, SELL, or CLOSE"}), 400

    now = datetime.now(timezone.utc).isoformat()
    signal_payload = {
        "user_id":     uid,
        "symbol":      symbol,
        "action":      action,
        "price":       data.get("price"),
        "timeframe":   "manual",
        "reason":      reason,
        "source":      "dashboard",
        "received_at": now,
    }

    try:
        sb = get_supabase()
        sb.table("signals").insert(signal_payload).execute()
    except Exception as exc:
        logger.warning("Failed to persist manual signal: %s", exc)

    # Push drawing to TradingView chart
    if data.get("price"):
        direction = "UP" if action == "BUY" else "DOWN"
        drawing_queue.add("SIGNAL_ARROW", {
            "price":     float(data["price"]),
            "direction": direction,
            "strategy":  "MANUAL",
            "label":     f"Manual {action}",
        })

    if _trade_executor:
        try:
            _trade_executor.on_signal({
                "symbol":  symbol,
                "action":  action,
                "price":   float(data.get("price") or 0),
                "reason":  reason,
            })
        except Exception:
            logger.exception("Manual trade execution failed.")
            return jsonify({"error": "Execution failed — see server log."}), 500

    return jsonify({"ok": True, "signal": signal_payload})


# ── API: Strategies ───────────────────────────────────────────────────────────

def _scan_strategies() -> List[Dict[str, Any]]:
    analysis_dir = ROOT / "analysis"
    results: List[Dict[str, Any]] = []
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
        class_name  = ""
        methods_count = 0
        try:
            source = py_file.read_text(encoding="utf-8")
            tree   = _ast.parse(source)
            description = (_ast.get_docstring(tree) or "").split("\n")[0].strip()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ClassDef):
                    if not class_name:
                        class_name = node.name
                    methods_count += sum(
                        1 for item in node.body
                        if isinstance(item, _ast.FunctionDef) and not item.name.startswith("_")
                    )
        except Exception:
            pass
        results.append({
            "id": stem, "display_name": display_name,
            "file": py_file.name, "class_name": class_name,
            "description": description, "methods_count": methods_count,
            "enabled": True,
        })
    return results


@app.get("/api/strategies")
@require_auth
def api_strategies():
    uid = current_user_id()
    strategies = _scan_strategies()
    # Merge per-user enable/disable from Supabase
    try:
        sb  = get_supabase()
        res = sb.table("strategy_configs").select("strategy_id, enabled").eq("user_id", uid).execute()
        overrides = {r["strategy_id"]: r["enabled"] for r in (res.data or [])}
        for s in strategies:
            if s["id"] in overrides:
                s["enabled"] = overrides[s["id"]]
    except Exception:
        pass
    return jsonify({"strategies": strategies, "count": len(strategies)})


@app.post("/api/strategies/<strategy_id>/toggle")
@require_auth
def api_strategy_toggle(strategy_id: str):
    uid     = current_user_id()
    enabled = request.get_json(force=True, silent=True) or {}
    enabled = bool(enabled.get("enabled", True))
    try:
        sb = get_supabase()
        sb.table("strategy_configs").upsert({
            "user_id": uid, "strategy_id": strategy_id,
            "enabled": enabled, "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"strategy_id": strategy_id, "enabled": enabled})


@app.get("/api/strategies/<strategy_id>")
@require_auth
def api_strategy_detail(strategy_id: str):
    analysis_dir = ROOT / "analysis"
    candidates   = list(analysis_dir.glob(f"{strategy_id}.py"))
    if not candidates:
        candidates = list(analysis_dir.glob(f"strategy_{strategy_id}.py"))
    if not candidates:
        return jsonify({"error": "Strategy not found"}), 404

    py_file = candidates[0]
    try:
        source     = py_file.read_text(encoding="utf-8")
        tree       = _ast.parse(source)
        module_doc = _ast.get_docstring(tree) or ""
        classes: List[Dict[str, Any]] = []

        for node in _ast.walk(tree):
            if not isinstance(node, _ast.ClassDef):
                continue
            class_doc  = _ast.get_docstring(node) or ""
            methods: List[Dict[str, Any]] = []
            init_params: List[str] = []

            for item in node.body:
                if not isinstance(item, _ast.FunctionDef):
                    continue
                if item.name.startswith("_") and item.name != "__init__":
                    continue
                m_doc  = _ast.get_docstring(item) or ""
                params = [a.arg for a in item.args.args if a.arg != "self"]
                if item.name == "__init__":
                    init_params = params
                else:
                    methods.append({"name": item.name, "doc": m_doc, "params": params})

            classes.append({"name": node.name, "doc": class_doc,
                            "init_params": init_params, "methods": methods})

        return jsonify({"id": py_file.stem, "file": py_file.name,
                        "module_doc": module_doc, "classes": classes})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── API: TradingView config ───────────────────────────────────────────────────

@app.get("/api/tradingview/config")
@require_auth
def api_tv_config_get():
    uid = current_user_id()
    try:
        sb  = get_supabase()
        res = sb.table("tv_config").select("*").eq("user_id", uid).single().execute()
        cfg = res.data or {}
        # Merge defaults for any missing keys
        merged = {**TV_CONFIG_DEFAULTS, **cfg}
        return jsonify(merged)
    except Exception:
        return jsonify(TV_CONFIG_DEFAULTS)


@app.post("/api/tradingview/config")
@require_auth
def api_tv_config_update():
    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    allowed = {"symbol", "interval", "theme", "style", "studies"}
    payload = {k: v for k, v in data.items() if k in allowed}
    payload["user_id"]    = uid
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        sb = get_supabase()
        sb.table("tv_config").upsert(payload).execute()
        res = sb.table("tv_config").select("*").eq("user_id", uid).single().execute()
        return jsonify(res.data or {**TV_CONFIG_DEFAULTS, **payload})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── API: TradingView accounts ─────────────────────────────────────────────────

@app.get("/api/tradingview/accounts")
@require_auth
def api_tv_accounts_list():
    uid = current_user_id()
    try:
        sb  = get_supabase()
        res = sb.table("tv_accounts").select("*").eq("user_id", uid).order("created_at").execute()
        cfg = sb.table("tv_config").select("active_tv_account_id").eq("user_id", uid).single().execute()
        active_id = (cfg.data or {}).get("active_tv_account_id")
        return jsonify({"accounts": res.data or [], "active_account_id": active_id})
    except Exception as exc:
        return jsonify({"accounts": [], "active_account_id": None})


@app.post("/api/tradingview/accounts")
@require_auth
def api_tv_accounts_create():
    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    row  = {
        "user_id":      uid,
        "tv_username":  data.get("username", "").strip(),
        "display_name": data.get("display_name", data.get("username", "Account")).strip(),
        "symbol":       data.get("symbol", "AMEX:SPY"),
        "interval":     data.get("interval", "5"),
        "theme":        data.get("theme", "dark"),
        "notes":        data.get("notes", ""),
        "is_active":    False,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        sb  = get_supabase()
        res = sb.table("tv_accounts").insert(row).execute()
        return jsonify(res.data[0] if res.data else row), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/tradingview/accounts/<account_id>/activate")
@require_auth
def api_tv_account_activate(account_id: str):
    uid = current_user_id()
    try:
        sb  = get_supabase()
        acc = sb.table("tv_accounts").select("*").eq("id", account_id).eq("user_id", uid).single().execute()
        if not acc.data:
            return jsonify({"error": "Not found"}), 404
        a   = acc.data
        cfg = {
            "user_id":              uid,
            "symbol":               a.get("symbol", "AMEX:SPY"),
            "interval":             a.get("interval", "5"),
            "theme":                a.get("theme", "dark"),
            "active_tv_account_id": account_id,
            "updated_at":           datetime.now(timezone.utc).isoformat(),
        }
        sb.table("tv_config").upsert(cfg).execute()
        res = sb.table("tv_config").select("*").eq("user_id", uid).single().execute()
        return jsonify(res.data or cfg)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.delete("/api/tradingview/accounts/<account_id>")
@require_auth
def api_tv_account_delete(account_id: str):
    uid = current_user_id()
    try:
        sb = get_supabase()
        sb.table("tv_accounts").delete().eq("id", account_id).eq("user_id", uid).execute()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── API: Groq AI ──────────────────────────────────────────────────────────────

@app.post("/api/ai/analyze-signal")
@require_auth
def api_ai_signal():
    data = request.get_json(force=True, silent=True) or {}
    try:
        from ai.groq_client import analyze_signal
        commentary = analyze_signal(data)
        return jsonify({"commentary": commentary})
    except Exception as exc:
        return jsonify({"commentary": f"AI unavailable: {exc}"}), 200


@app.post("/api/ai/analyze-pnl")
@require_auth
def api_ai_pnl():
    data = request.get_json(force=True, silent=True) or {}
    try:
        from ai.groq_client import analyze_pnl
        commentary = analyze_pnl(data)
        return jsonify({"commentary": commentary})
    except Exception as exc:
        return jsonify({"commentary": f"AI unavailable: {exc}"}), 200


@app.post("/api/ai/chat")
@require_auth
def api_ai_chat():
    data     = request.get_json(force=True, silent=True) or {}
    messages = data.get("messages", [])
    system   = data.get("system", "You are a professional trading assistant for Lucid AI Trader. Be concise and helpful.")
    try:
        from ai.groq_client import chat
        reply = chat(messages, system=system)
        return jsonify({"reply": reply})
    except Exception as exc:
        return jsonify({"reply": f"Error: {exc}"}), 200


# ── API: AI Chat Sessions (persistent) ───────────────────────────────────────

_CHAT_SYSTEM = (
    "You are Lucid AI, an expert trading assistant specializing in futures markets "
    "(MES, MNQ, ES, NQ, and others). You help traders analyze markets, plan strategies, "
    "review performance, and understand professional trading concepts including ICT, SMC, "
    "ORB, liquidity sweeps, VWAP, fair value gaps, order blocks, and market structure. "
    "Be concise, clear, and actionable. Always mention risk management when discussing trades."
)


@app.get("/api/ai/chat/sessions")
@require_auth
def api_chat_sessions_list():
    uid = current_user_id()
    try:
        sb  = get_supabase()
        res = (sb.table("chat_sessions")
                 .select("id, title, created_at, updated_at")
                 .eq("user_id", uid)
                 .order("updated_at", desc=True)
                 .limit(50)
                 .execute())
        return jsonify({"sessions": res.data or []})
    except Exception as exc:
        return jsonify({"sessions": [], "error": str(exc)})


@app.post("/api/ai/chat/sessions")
@require_auth
def api_chat_sessions_create():
    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    now  = datetime.now(timezone.utc).isoformat()
    try:
        sb  = get_supabase()
        res = sb.table("chat_sessions").insert({
            "user_id":    uid,
            "title":      data.get("title", "New Chat"),
            "created_at": now,
            "updated_at": now,
        }).execute()
        return jsonify(res.data[0] if res.data else {}), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/ai/chat/sessions/<session_id>")
@require_auth
def api_chat_session_get(session_id: str):
    uid = current_user_id()
    try:
        sb   = get_supabase()
        sess = (sb.table("chat_sessions")
                  .select("*")
                  .eq("id", session_id)
                  .eq("user_id", uid)
                  .single()
                  .execute())
        if not sess.data:
            return jsonify({"error": "Not found"}), 404
        msgs = (sb.table("chat_messages")
                  .select("id, role, content, created_at")
                  .eq("session_id", session_id)
                  .order("created_at")
                  .execute())
        return jsonify({"session": sess.data, "messages": msgs.data or []})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/ai/chat/sessions/<session_id>/message")
@require_auth
def api_chat_session_message(session_id: str):
    uid     = current_user_id()
    data    = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    try:
        sb = get_supabase()

        # Verify session belongs to user
        sess = (sb.table("chat_sessions")
                  .select("id")
                  .eq("id", session_id)
                  .eq("user_id", uid)
                  .single()
                  .execute())
        if not sess.data:
            return jsonify({"error": "Session not found"}), 404

        # Fetch history
        history_res = (sb.table("chat_messages")
                         .select("role, content")
                         .eq("session_id", session_id)
                         .order("created_at")
                         .execute())
        history = history_res.data or []

        # Save user message
        sb.table("chat_messages").insert({
            "session_id": session_id,
            "user_id":    uid,
            "role":       "user",
            "content":    content,
            "created_at": now,
        }).execute()

        # Build message list for Groq (full history + new message)
        groq_messages = [{"role": m["role"], "content": m["content"]} for m in history]
        groq_messages.append({"role": "user", "content": content})

        from ai.groq_client import chat as groq_chat
        reply = groq_chat(groq_messages, system=_CHAT_SYSTEM)

        # Save assistant reply
        reply_now = datetime.now(timezone.utc).isoformat()
        sb.table("chat_messages").insert({
            "session_id": session_id,
            "user_id":    uid,
            "role":       "assistant",
            "content":    reply,
            "created_at": reply_now,
        }).execute()

        # Update session timestamp; auto-title on first message
        update_payload: Dict[str, Any] = {"updated_at": reply_now}
        if not history:
            update_payload["title"] = content[:60] + ("…" if len(content) > 60 else "")
        sb.table("chat_sessions").update(update_payload).eq("id", session_id).execute()

        return jsonify({"reply": reply, "session_id": session_id})

    except Exception as exc:
        logger.exception("Chat message error")
        return jsonify({"reply": f"Error: {exc}", "session_id": session_id}), 200


@app.delete("/api/ai/chat/sessions/<session_id>")
@require_auth
def api_chat_session_delete(session_id: str):
    uid = current_user_id()
    try:
        sb = get_supabase()
        sb.table("chat_sessions").delete().eq("id", session_id).eq("user_id", uid).execute()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── API: Trading Mode ─────────────────────────────────────────────────────────

@app.get("/api/mode")
@require_auth
def api_mode_get():
    uid     = current_user_id()
    account = get_account_manager().get_active_account(uid)
    if not account:
        # Fall back to session-stored mode (no account required)
        return jsonify({
            "trading_mode":   session.get("trading_mode", "SEMI_AUTO"),
            "autonomous_mode": False,
            "account": None,
        })
    return jsonify({
        "trading_mode":   account.get("trading_mode", "SEMI_AUTO"),
        "autonomous_mode": account.get("autonomous_mode", False),
        "account_id":     account.get("id"),
        "account_name":   account.get("name"),
    })


@app.post("/api/mode")
@require_auth
def api_mode_set():
    from core.state_manager import TRADING_MODES
    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    mode = (data.get("mode") or "").upper()
    if mode not in TRADING_MODES:
        return jsonify({"error": f"Invalid mode '{mode}'. Must be one of: {', '.join(TRADING_MODES)}"}), 400
    account = get_account_manager().get_active_account(uid)
    if not account:
        # No account — persist in session so the UI still reflects the choice
        session["trading_mode"] = mode
        get_state_manager()._session_mode = mode
        return jsonify({"trading_mode": mode, "ok": True, "note": "Saved to session (no active account)"})
    ok = get_state_manager().set_trading_mode(mode, account["id"], uid)
    if not ok:
        return jsonify({"error": f"Failed to save mode '{mode}' — check server logs"}), 500
    return jsonify({"trading_mode": mode, "ok": True})


# ── API: Brokers ──────────────────────────────────────────────────────────────

@app.get("/api/brokers")
@require_auth
def api_brokers_list():
    """Return all brokers with connection status."""
    return jsonify({"brokers": broker_registry.list_all(), "active": broker_registry.active_name})


@app.post("/api/brokers/<broker_name>/connect")
@require_auth
def api_broker_connect(broker_name: str):
    credentials = request.get_json(force=True, silent=True) or {}
    ok, msg = broker_registry.connect(broker_name, **credentials)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "message": msg, "active": broker_registry.active_name})


@app.post("/api/brokers/<broker_name>/activate")
@require_auth
def api_broker_activate(broker_name: str):
    ok, msg = broker_registry.switch_to(broker_name)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "message": msg, "active": broker_registry.active_name})


@app.post("/api/brokers/<broker_name>/disconnect")
@require_auth
def api_broker_disconnect(broker_name: str):
    if broker_name == "paper":
        return jsonify({"error": "Cannot disconnect paper trading — it is always available."}), 400
    broker_registry.disconnect(broker_name)
    return jsonify({"ok": True, "active": broker_registry.active_name})


@app.get("/api/brokers/active")
@require_auth
def api_broker_active():
    broker = broker_registry.active
    return jsonify({
        "active": broker_registry.active_name,
        "display_name": broker.display_name,
        "connected": broker.is_connected(),
        "balance": broker.get_account_balance(),
        "positions": [
            {"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price, "side": p.side}
            for p in broker.get_positions()
        ],
    })


# ── API: Backtesting ──────────────────────────────────────────────────────────

@app.get("/api/backtest/strategies")
@require_auth
def api_backtest_strategies():
    from backtesting.engine import list_strategies
    return jsonify({"strategies": list_strategies()})


@app.post("/api/backtest/run")
@require_auth
def api_backtest_run():
    data             = request.get_json(force=True, silent=True) or {}
    strategy_name    = data.get("strategy_name", "")
    symbol           = data.get("symbol", "")
    start            = data.get("start", "")
    end              = data.get("end", "")
    interval         = data.get("interval", "5m")
    starting_balance = float(data.get("starting_balance", 100_000))
    qty              = int(data.get("qty", 1))
    params           = data.get("params") or {}

    if not all([strategy_name, symbol, start, end]):
        return jsonify({"error": "strategy_name, symbol, start, and end are required"}), 400

    try:
        from backtesting.engine import run_backtest
        result = run_backtest(
            strategy_name=strategy_name,
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
            starting_balance=starting_balance,
            qty=qty,
            params=params,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Backtest run failed")
        return jsonify({"error": f"Backtest failed: {exc}"}), 500


# ── API: Accounts ─────────────────────────────────────────────────────────────

@app.get("/api/accounts")
@require_auth
def api_accounts_list():
    uid = current_user_id()
    return jsonify({"accounts": get_account_manager().get_all_accounts(uid)})


@app.post("/api/accounts")
@require_auth
def api_accounts_create():
    uid  = current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    account = get_account_manager().add_account(
        user_id=uid,
        name=data.get("name", "New Account"),
        account_type=data.get("account_type", "PERSONAL_LIVE"),
        risk_mode=data.get("risk_mode", "BALANCED"),
        starting_balance=float(data.get("starting_balance", 0)),
        daily_loss_limit=float(data.get("daily_loss_limit", 0)),
        max_drawdown_pct=float(data.get("max_drawdown_pct", 5.0)),
        max_contracts=int(data.get("max_contracts", 1)),
        broker=data.get("broker", "tradovate"),
        trading_mode=data.get("trading_mode", "SEMI_AUTO"),
        is_evaluation_phase=bool(data.get("is_evaluation_phase", False)),
        notes=data.get("notes", ""),
    )
    if not account:
        return jsonify({"error": "Failed to create account"}), 500
    return jsonify(account), 201


@app.post("/api/accounts/switch")
@require_auth
def api_accounts_switch():
    uid        = current_user_id()
    data       = request.get_json(force=True, silent=True) or {}
    account_id = data.get("account_id", "")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    ok, message = get_account_manager().switch_account(uid, account_id)
    if not ok:
        return jsonify({"error": message}), 404
    account = get_account_manager().get_active_account(uid)
    if account and _telegram_bot:
        _telegram_bot.send_message(
            f"Switched to: {account['name']} | "
            f"Balance: ${account.get('current_balance', 0):,.0f} | "
            f"Mode: {account.get('risk_mode', '?')}"
        )
    emit_socket_event("account_switched", account or {})
    return jsonify({"ok": True, "account": account, "message": message})


# ── API: Risk Status ──────────────────────────────────────────────────────────

@app.get("/api/risk/status")
@require_auth
def api_risk_status():
    uid     = current_user_id()
    account = get_account_manager().get_active_account(uid)
    if not account:
        return jsonify({"error": "No active account"})
    return jsonify(get_risk_manager().get_risk_status(account))


# ── API: Strategy Performance ─────────────────────────────────────────────────

@app.get("/api/performance/strategies")
@require_auth
def api_strategy_performance():
    uid        = current_user_id()
    date_range = request.args.get("range", "all")
    strategy   = request.args.get("strategy", "")
    pe         = get_performance_engine()
    if strategy:
        stats = pe.get_strategy_stats(strategy.upper(), date_range, uid)
        return jsonify({"strategy": stats})
    all_stats = pe.get_all_strategies_report(date_range, uid)
    return jsonify({"strategies": all_stats, "range": date_range})


# ── API: Autonomous Mode ──────────────────────────────────────────────────────

@app.post("/api/autonomous/toggle")
@require_auth
def api_autonomous_toggle():
    uid       = current_user_id()
    data      = request.get_json(force=True, silent=True) or {}
    enable    = bool(data.get("enable", False))
    confirmed = bool(data.get("confirmed", False))
    account   = get_account_manager().get_active_account(uid)
    if not account:
        return jsonify({"error": "No active account"}), 400
    result = get_state_manager().toggle_autonomous_mode(enable, account["id"], uid, confirmed)
    return jsonify(result)


# ── API: Pending signal (SEMI_AUTO dashboard polling) ─────────────────────────

@app.get("/api/signals/pending")
@require_auth
def api_signals_pending():
    pending = get_state_manager().get_pending_signal()
    return jsonify({"pending": pending})


@app.post("/api/signals/<signal_id>/approve")
@require_auth
def api_signal_approve(signal_id: str):
    ok = get_state_manager().set_approval_result(signal_id, True)
    return jsonify({"ok": ok})


@app.post("/api/signals/<signal_id>/reject")
@require_auth
def api_signal_reject(signal_id: str):
    ok = get_state_manager().set_approval_result(signal_id, False)
    return jsonify({"ok": ok})


# ── TradingView public URL ────────────────────────────────────────────────────

def get_public_url() -> str:
    """Return the public-facing URL — prefers a running ngrok tunnel."""
    import requests as _requests
    try:
        resp = _requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = resp.json().get("tunnels", [])
        https_url = next(
            (t["public_url"] for t in tunnels if t.get("proto") == "https"),
            None,
        )
        if https_url:
            return https_url
    except Exception:
        pass
    return os.getenv("PUBLIC_URL", "http://localhost:8080")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_boundary_label(session: str) -> str:
    return {
        "Globex":     "Pre-market open",
        "Pre-market": "RTH open",
        "RTH":        "Market close",
        "AH":         "Globex open",
        "Closed":     "Next session",
    }.get(session, "Next session")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true",
                        help="Verify routes and SocketIO init, then exit")
    args = parser.parse_args()

    _init_systems()

    if args.check_only:
        routes = sorted(rule.rule for rule in app.url_map.iter_rules())
        print(f"Routes registered: {len(routes)}")
        for r in routes:
            print(f"  {r}")
        print("SocketIO: OK")
        print("check-only passed")
        sys.exit(0)

    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    logger.info("Lucid AI Trader starting on http://localhost:%s", port)
    public_url = get_public_url()
    logger.info("TradingView webhook URL: %s/api/tv/webhook", public_url)
    logger.info("Copy this URL into your TradingView alert settings.")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
