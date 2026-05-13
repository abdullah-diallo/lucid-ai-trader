"""
alerts/telegram_bot.py
========================
Telegram bot for Lucid AI Trader.

Architecture:
  - Bot runs in a daemon thread with its own asyncio event loop.
  - Flask (synchronous) calls send_* methods, which use
    asyncio.run_coroutine_threadsafe(coro, self._loop) to safely cross
    the thread boundary.
  - All command handlers are async and run inside the bot thread.

Environment variables:
  TELEGRAM_BOT_TOKEN   — from BotFather
  TELEGRAM_CHAT_ID     — your personal chat ID (or group)
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _get_chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


class TelegramBot:
    """
    Thread-safe Telegram bot wrapper.

    Inject dependencies after construction to break circular imports:
        bot.set_state_manager(state_manager)
        bot.set_performance_engine(perf_engine)
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app = None
        self._state_manager = None
        self._performance_engine = None
        self._account_manager = None
        self._self_improvement_engine = None
        self._risk_manager = None

    # ── Dependency injection ──────────────────────────────────────────────────

    def set_state_manager(self, sm) -> None:
        self._state_manager = sm

    def set_performance_engine(self, pe) -> None:
        self._performance_engine = pe

    def set_account_manager(self, am) -> None:
        self._account_manager = am

    def set_self_improvement_engine(self, sie) -> None:
        self._self_improvement_engine = sie

    def set_risk_manager(self, rm) -> None:
        self._risk_manager = rm

    # ── Startup ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the bot in a background daemon thread."""
        token = _get_token()
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled.")
            return
        t = threading.Thread(target=self._run_bot, daemon=True, name="telegram-bot")
        t.start()
        logger.info("Telegram bot thread started.")

    def _run_bot(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception:
            logger.exception("Telegram bot crashed.")

    async def _async_main(self) -> None:
        try:
            from telegram.ext import (Application, CallbackQueryHandler,
                                       CommandHandler)
        except ImportError:
            logger.error(
                "python-telegram-bot is not installed. "
                "Run: pip install python-telegram-bot>=21.0"
            )
            return

        token = _get_token()
        app = (
            Application.builder()
            .token(token)
            .build()
        )
        self._app = app

        app.add_handler(CommandHandler("mode",       self._cmd_mode))
        app.add_handler(CommandHandler("autonomous", self._cmd_autonomous))
        app.add_handler(CommandHandler("performance",self._cmd_performance))
        app.add_handler(CommandHandler("status",     self._cmd_status))
        app.add_handler(CommandHandler("strategies", self._cmd_strategies))
        app.add_handler(CommandHandler("pause",      self._cmd_pause))
        app.add_handler(CommandHandler("resume",     self._cmd_resume))
        app.add_handler(CommandHandler("halt",       self._cmd_halt))
        app.add_handler(CommandHandler("accounts",   self._cmd_accounts))
        app.add_handler(CommandHandler("switch",     self._cmd_switch))
        app.add_handler(CommandHandler("report",     self._cmd_report))
        app.add_handler(CommandHandler("help",       self._cmd_help))
        app.add_handler(CommandHandler("start",      self._cmd_help))
        app.add_handler(CallbackQueryHandler(self._callback_handler))
        from telegram.ext import MessageHandler, filters as tg_filters
        app.add_handler(MessageHandler(tg_filters.COMMAND, self._cmd_unknown))

        logger.info("Telegram bot polling…")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # Keep running forever
        await asyncio.Event().wait()

    # ── Command handlers ──────────────────────────────────────────────────────

    async def _cmd_help(self, update, context) -> None:
        await update.message.reply_text(
            "🤖 *Lucid AI Trader — Commands*\n\n"
            "/status — Balance, P&L, and trading state\n"
            "/performance \\[today|week|month\\] — Performance report\n"
            "/performance custom YYYY\\-MM\\-DD YYYY\\-MM\\-DD — Custom range\n"
            "/strategies — All strategies with active/paused badge\n"
            "/pause \\[CODE\\] — Pause a specific strategy\n"
            "/resume \\[CODE\\] — Resume strategy or trading\n"
            "/mode \\[auto|semiauto|signals\\] — Switch trading mode\n"
            "/halt — Emergency stop\n"
            "/autonomous \\[on|off|status\\] — Toggle autonomous mode\n"
            "/accounts — List all accounts\n"
            "/switch \\[name\\] — Switch active account\n"
            "/report — Today's performance summary\n"
            "/help — This message",
            parse_mode="MarkdownV2",
        )

    async def _cmd_mode(self, update, context) -> None:
        args   = context.args or []
        cmd    = args[0].lower() if args else "status"
        sm     = self._state_manager
        am     = self._account_manager
        chat   = str(update.effective_chat.id)

        if not sm or not am:
            await update.message.reply_text("⚠️ System not ready.")
            return

        # Derive user from chat_id (simplified: only single-user setups)
        uid    = _get_chat_id()  # reuse the stored chat id as a proxy user key

        if cmd == "status":
            accts = am.get_all_accounts(uid) if uid else []
            if not accts:
                await update.message.reply_text("No accounts configured.")
                return
            lines = []
            for a in accts:
                active = "✅" if a.get("is_active") else "  "
                lines.append(f"{active} {a['name']}: {a['trading_mode']} / {a['risk_mode']}")
            await update.message.reply_text("📊 Account Modes:\n" + "\n".join(lines))
            return

        mode_map = {"auto": "FULL_AUTO", "semiauto": "SEMI_AUTO", "signals": "SIGNALS_ONLY"}
        mode = mode_map.get(cmd)
        if not mode:
            await update.message.reply_text(
                "Usage: /mode auto|semiauto|signals|status"
            )
            return

        account = am.get_active_account(uid) if uid else None
        if not account:
            await update.message.reply_text("No active account found.")
            return

        ok = sm.set_trading_mode(mode, account["id"], uid)
        if ok:
            await update.message.reply_text(f"✅ Mode set to *{mode}*.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Failed to update mode.")

    async def _cmd_autonomous(self, update, context) -> None:
        args = context.args or []
        cmd  = args[0].lower() if args else "status"
        sm   = self._state_manager
        am   = self._account_manager
        uid  = _get_chat_id()

        if not sm or not am:
            await update.message.reply_text("⚠️ System not ready.")
            return

        account = am.get_active_account(uid) if uid else None
        if not account:
            await update.message.reply_text("No active account found.")
            return

        if cmd == "status":
            state = "ENABLED 🟢" if account.get("autonomous_mode") else "DISABLED 🔴"
            await update.message.reply_text(f"Autonomous mode: {state}")
            return

        if cmd in ("on", "off"):
            enable = (cmd == "on")
            result = sm.toggle_autonomous_mode(enable, account["id"], uid, confirmed=False)
            if result["status"] == "confirm_required":
                await update.message.reply_text(result["message"])
                # Next message with "CONFIRM" will be handled via conversation or re-command
            elif result["status"] == "error":
                await update.message.reply_text(f"❌ {result['message']}")
            else:
                state = "enabled" if enable else "disabled"
                await update.message.reply_text(f"✅ Autonomous mode {state}.")
            return

        # Handle "CONFIRM" as text confirmation for enabling autonomous mode
        if cmd == "confirm":
            result = sm.toggle_autonomous_mode(True, account["id"], uid, confirmed=True)
            if result["status"] == "ok":
                await update.message.reply_text("🟢 Autonomous mode ENABLED.")
            else:
                await update.message.reply_text(f"❌ {result['message']}")
            return

        await update.message.reply_text("Usage: /autonomous on|off|status")

    async def _cmd_performance(self, update, context) -> None:
        args = context.args or []
        pe   = self._performance_engine
        uid  = _get_chat_id()

        if not pe:
            await update.message.reply_text("Performance engine not available.")
            return

        date_range = "all"
        strategy_name = None

        if args:
            first = args[0].lower()
            if first in ("today", "week", "month", "all"):
                date_range = first
            elif first == "custom" and len(args) >= 3:
                date_range = (args[1], args[2])
            else:
                strategy_name = " ".join(args).upper()

        if strategy_name:
            stats = pe.get_strategy_stats(strategy_name, date_range, uid)
            text  = pe.format_telegram_performance_report(stats)
        else:
            all_stats = pe.get_all_strategies_report(date_range, uid)
            text      = pe.format_all_strategies_telegram(all_stats, date_range)

        await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_resume(self, update, context) -> None:
        args = context.args or []
        if args:
            code = args[0].upper()
            from analysis.strategy_registry import STRATEGY_REGISTRY
            if code in STRATEGY_REGISTRY:
                STRATEGY_REGISTRY[code]["active"] = True
                logger.info("Strategy %s resumed via /resume", code)
                await update.message.reply_text(f"▶️ Strategy {code} resumed.")
            else:
                await update.message.reply_text(
                    f"Unknown strategy: {code}. Send /strategies to see all codes."
                )
            return
        rm = self._risk_manager
        if rm:
            rm.is_trading_halted = False
            rm.halt_reason = ""
        logger.info("Trading resumed via /resume")
        await update.message.reply_text(
            "▶️ Trading resumed. The next valid signal will be processed.\n"
            "Ensure you have reviewed your account before continuing."
        )

    async def _cmd_status(self, update, context) -> None:
        am  = self._account_manager
        uid = _get_chat_id()
        if not am:
            await update.message.reply_text("⚠️ System not ready.")
            return
        account = am.get_active_account(uid)
        if not account:
            await update.message.reply_text("No active account found.")
            return
        name      = account.get("name", "?")
        balance   = float(account.get("current_balance", 0))
        mode      = account.get("trading_mode", "?")
        daily_pnl = float(account.get("daily_pnl", 0))
        dll       = float(account.get("daily_loss_limit", 0))
        dll_pct   = abs(daily_pnl) / dll * 100 if dll > 0 else 0
        rm        = self._risk_manager
        halted    = rm.is_trading_halted if rm else False
        await update.message.reply_text(
            f"Account: {name} | Balance: ${balance:,.2f} | Mode: {mode}\n"
            f"Today P&L: ${daily_pnl:+.2f} | DLL used: {dll_pct:.0f}%\n"
            f"Open positions: —\n"
            f"Trading: {'ACTIVE' if not halted else 'HALTED'}"
        )

    async def _cmd_strategies(self, update, context) -> None:
        from analysis.strategy_registry import STRATEGY_REGISTRY
        lines = []
        for code, info in STRATEGY_REGISTRY.items():
            badge = "✅" if info.get("active", True) else "⏸"
            lines.append(f"{badge} {code}")
        chunks = [lines[i:i + 20] for i in range(0, len(lines), 20)]
        for chunk in chunks:
            await update.message.reply_text("\n".join(chunk))

    async def _cmd_pause(self, update, context) -> None:
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: /pause [STRATEGY\\_CODE]", parse_mode="Markdown")
            return
        code = args[0].upper()
        from analysis.strategy_registry import STRATEGY_REGISTRY
        if code not in STRATEGY_REGISTRY:
            await update.message.reply_text(
                f"Unknown strategy: {code}. Send /strategies to list all codes."
            )
            return
        STRATEGY_REGISTRY[code]["active"] = False
        logger.info("Strategy %s paused via /pause", code)
        await update.message.reply_text(f"⏸ Strategy {code} paused.")

    async def _cmd_halt(self, update, context) -> None:
        rm = self._risk_manager
        if rm:
            rm.is_trading_halted = True
            rm.halt_reason = "Emergency halt via Telegram /halt"
            logger.warning("Emergency halt activated via /halt")
            await update.message.reply_text(
                "🛑 EMERGENCY HALT activated.\nAll new signals will be blocked.\n"
                "Send /resume to restart."
            )
        else:
            await update.message.reply_text("⚠️ Risk manager not available.")

    async def _cmd_accounts(self, update, context) -> None:
        am  = self._account_manager
        uid = _get_chat_id()
        if not am:
            await update.message.reply_text("⚠️ System not ready.")
            return
        accounts = am.get_all_accounts(uid) or []
        if not accounts:
            await update.message.reply_text("No accounts configured.")
            return
        lines = []
        for a in accounts:
            active  = "✅" if a.get("is_active") else "  "
            atype   = a.get("account_type", "?")
            bal     = float(a.get("current_balance", 0))
            rmode   = a.get("risk_mode", "?")
            lines.append(f"{active} {a['name']} [{atype}] ${bal:,.0f} | {rmode}")
        await update.message.reply_text("💼 Accounts:\n" + "\n".join(lines))

    async def _cmd_switch(self, update, context) -> None:
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: /switch [account name]")
            return
        name = " ".join(args)
        am   = self._account_manager
        uid  = _get_chat_id()
        if not am:
            await update.message.reply_text("⚠️ System not ready.")
            return
        accounts = am.get_all_accounts(uid) or []
        target = next(
            (a for a in accounts if a.get("name", "").lower() == name.lower()), None
        )
        if not target:
            await update.message.reply_text(
                f"Account '{name}' not found. Send /accounts to list."
            )
            return
        ok = am.switch_account(uid, target["id"])
        if ok:
            logger.info("Account switched to %s via /switch", target["name"])
            await update.message.reply_text(f"🔄 Switched to: {target['name']}")
        else:
            await update.message.reply_text("❌ Failed to switch account.")

    async def _cmd_report(self, update, context) -> None:
        pe  = self._performance_engine
        uid = _get_chat_id()
        if not pe:
            await update.message.reply_text("Performance engine not available.")
            return
        all_stats = pe.get_all_strategies_report("today", uid)
        text = pe.format_all_strategies_telegram(all_stats, "today")
        await update.message.reply_text(f"📊 Daily Report\n{text}", parse_mode="Markdown")

    async def _cmd_unknown(self, update, context) -> None:
        await update.message.reply_text("Unknown command. Send /help to see all commands.")

    # ── Callback handler (inline keyboard buttons) ────────────────────────────

    async def _callback_handler(self, update, context) -> None:
        query = update.callback_query
        await query.answer()
        data  = query.data or ""
        sm    = self._state_manager

        if data.startswith("approve_") and sm:
            signal_id = data[len("approve_"):]
            ok = sm.set_approval_result(signal_id, True)
            await query.edit_message_text(
                query.message.text + "\n\n✅ *Approved*", parse_mode="Markdown"
            )

        elif data.startswith("reject_") and sm:
            signal_id = data[len("reject_"):]
            sm.set_approval_result(signal_id, False)
            await query.edit_message_text(
                query.message.text + "\n\n❌ *Rejected*", parse_mode="Markdown"
            )

        elif data.startswith("override_approve_") and sm:
            # Strip "override_approve_" to get original signal_id
            signal_id = data[len("override_approve_"):]
            sm.set_approval_result(f"override_{signal_id}", True)
            await query.edit_message_text(
                query.message.text + "\n\n🔥 *Override APPROVED*", parse_mode="Markdown"
            )

        elif data.startswith("override_skip_") and sm:
            signal_id = data[len("override_skip_"):]
            sm.set_approval_result(f"override_{signal_id}", False)
            await query.edit_message_text(
                query.message.text + "\n\n❌ *Override skipped*", parse_mode="Markdown"
            )

        elif data.startswith("undo_"):
            improvement_id = data[len("undo_"):]
            sie = self._self_improvement_engine
            if sie:
                ok = sie.revert_improvement(improvement_id)
                msg = "✅ Improvement reverted." if ok else "❌ Could not revert improvement."
            else:
                msg = "❌ Self-improvement engine not available."
            await query.edit_message_text(query.message.text + f"\n\n{msg}")

        elif data.startswith("unpause_"):
            strategy_name = data[len("unpause_"):]
            sie = self._self_improvement_engine
            am  = self._account_manager
            uid = _get_chat_id()
            if sie and am:
                account = am.get_active_account(uid) if uid else None
                uid_real = (account or {}).get("user_id") or uid
                ok = sie.unpause_strategy(strategy_name, uid_real)
                msg = f"✅ Strategy *{strategy_name}* unpaused." if ok else "❌ Failed to unpause."
            else:
                msg = "❌ System not ready."
            await query.edit_message_text(msg, parse_mode="Markdown")

        elif data.startswith("manual_yes_"):
            signal_id = data[len("manual_yes_"):]
            if sm:
                sm.set_manual_track_result(signal_id, True)
            await query.edit_message_text(
                query.message.text + "\n\n✅ *Logged as taken.*", parse_mode="Markdown"
            )

        elif data.startswith("manual_no_"):
            signal_id = data[len("manual_no_"):]
            if sm:
                sm.set_manual_track_result(signal_id, False)
            await query.edit_message_text(
                query.message.text + "\n\n❌ *Logged as pass.*", parse_mode="Markdown"
            )

    # ── Push notification methods ─────────────────────────────────────────────

    def format_approval_alert(self, signal: Dict[str, Any], probability: Dict[str, Any]) -> str:
        """HTML-formatted semi-auto approval message."""
        instrument  = signal.get("instrument", signal.get("symbol", "?"))
        action      = str(signal.get("action", "")).upper()
        direction   = signal.get("direction", "LONG" if action == "BUY" else "SHORT")
        dir_emoji   = "🟢" if direction == "LONG" else "🔴"
        conf_pct    = int(float(signal.get("confidence", 0)) * 100)
        prob_str    = probability.get("display_string", f"{conf_pct}%")
        factors     = " · ".join(signal.get("confluence_factors", [])[:3])
        strategy    = signal.get("strategy_full_name", signal.get("strategy", "?"))
        session     = signal.get("session", "")

        ts = signal.get("time_et", "")
        if not ts:
            ts_raw = signal.get("timestamp", "")
            try:
                ts = ts_raw.strftime("%H:%M ET") if hasattr(ts_raw, "strftime") else str(ts_raw)[:16]
            except Exception:
                ts = ""

        entry = signal.get("entry", signal.get("price", 0))
        stop  = signal.get("stop_loss", signal.get("stop", 0))
        t1    = signal.get("t1", signal.get("take_profit_1", signal.get("target_1", 0)))
        t2    = signal.get("t2", signal.get("take_profit_2", signal.get("target_2", 0)))
        t3    = signal.get("t3", signal.get("take_profit_3", signal.get("target_3", 0)))

        def _pts(a, b):
            try:
                return abs(float(a) - float(b))
            except Exception:
                return 0.0

        stop_pts    = signal.get("stop_pts", _pts(entry, stop))
        stop_dollars = signal.get("stop_dollars", stop_pts * 5)
        t1_pts      = signal.get("t1_pts", _pts(t1, entry))
        t2_pts      = signal.get("t2_pts", _pts(t2, entry))
        t3_pts      = signal.get("t3_pts", _pts(t3, entry))
        rr1 = signal.get("rr1", signal.get("risk_reward_t1",
                          round(t1_pts / stop_pts, 1) if stop_pts else 0))
        rr2 = signal.get("rr2", signal.get("risk_reward_t2",
                          round(t2_pts / stop_pts, 1) if stop_pts else 0))
        rr3 = signal.get("rr3", round(t3_pts / stop_pts, 1) if stop_pts else 0)

        def _f(v):
            try:
                return f"{float(v):.2f}"
            except Exception:
                return str(v)

        return (
            f"{dir_emoji} <b>{instrument} {direction}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ <b>{strategy}</b>\n"
            f"⏰ {ts} · {session}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 Entry:  <code>{_f(entry)}</code>\n"
            f"🛑 Stop:   <code>{_f(stop)}</code>  (-{stop_pts:.2f}pts · ${stop_dollars:.0f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 T1: <code>{_f(t1)}</code>  +{t1_pts:.2f}pts  R:{rr1:.1f}\n"
            f"🎯 T2: <code>{_f(t2)}</code>  +{t2_pts:.2f}pts  R:{rr2:.1f}\n"
            f"🎯 T3: <code>{_f(t3)}</code>  +{t3_pts:.2f}pts  R:{rr3:.1f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 {signal.get('reason', '')}\n"
            f"📊 {prob_str}\n"
            f"🔗 {factors}"
        )

    def format_signals_only_alert(self, signal: Dict[str, Any], probability: Dict[str, Any]) -> str:
        """format_approval_alert plus SIGNALS ONLY footer."""
        header      = self.format_approval_alert(signal, probability)
        expiry      = signal.get("expiry_mins", 8)
        invalidation = signal.get("invalidation", signal.get("invalidation_level", "N/A"))
        return (
            header
            + f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ SIGNALS ONLY — Enter manually\n"
            f"⏳ Valid ~{expiry} min\n"
            f"❌ Invalidates if: <code>{invalidation}</code>"
        )

    def send_signal_alert(
        self,
        signal: Dict[str, Any],
        mode: str,
        probability: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Route to SEMI_AUTO approval request or SIGNALS_ONLY detailed alert."""
        prob = probability or {}
        if mode == "SEMI_AUTO":
            self._send_nowait(self._async_send_semi_auto_alert(signal, prob))
        elif mode == "SIGNALS_ONLY":
            self._send_nowait(self._async_send_signals_only_alert(signal, prob))

    def send_trade_executed(self, signal: Dict[str, Any], result: Dict[str, Any]) -> None:
        direction = "LONG" if str(signal.get("action", "")).upper() == "BUY" else "SHORT"
        symbol    = signal.get("symbol", "?")
        entry     = signal.get("entry", signal.get("price", "?"))
        text = f"✅ AUTO TRADE PLACED: {symbol} {direction} @ {entry}"
        self.send_message(text)

    def send_risk_alert(self, level: int, message: str) -> None:
        self.send_message(message)

    def send_override_request(
        self, signal: Dict[str, Any], override_details: Dict[str, Any]
    ) -> None:
        self._send_nowait(self._async_send_override_request(signal, override_details))

    def send_message(self, text: str) -> None:
        self._send_nowait(self._async_send_text(text))

    # ── Async send helpers ────────────────────────────────────────────────────

    def _send_nowait(self, coro) -> None:
        """Cross-thread coroutine dispatch."""
        if self._loop is None or self._loop.is_closed():
            logger.warning("Telegram: event loop not ready — message dropped.")
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _async_send_text(self, text: str) -> None:
        chat_id = _get_chat_id()
        if not chat_id or not self._app:
            return
        try:
            await self._app.bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception("Failed to send Telegram message.")

    async def _async_send_semi_auto_alert(
        self, signal: Dict[str, Any], probability: Dict[str, Any]
    ) -> None:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return

        chat_id   = _get_chat_id()
        signal_id = signal.get("_signal_id", "unknown")
        text      = self.format_approval_alert(signal, probability)
        text      = f"⏳ <b>APPROVAL REQUEST — SEMI AUTO</b>\n{text}\n⏱ You have 60 seconds."

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve",    callback_data=f"approve_{signal_id}"),
                InlineKeyboardButton("❌ Skip",        callback_data=f"reject_{signal_id}"),
                InlineKeyboardButton("⏸ Snooze 5min", callback_data=f"snooze_{signal_id}"),
            ]
        ])

        if chat_id and self._app:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception("Failed to send SEMI_AUTO alert.")

    async def _async_send_signals_only_alert(
        self, signal: Dict[str, Any], probability: Dict[str, Any]
    ) -> None:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return

        chat_id   = _get_chat_id()
        signal_id = signal.get("_signal_id", "unknown")
        text      = self.format_signals_only_alert(signal, probability)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✔️ Took It", callback_data=f"manual_yes_{signal_id}"),
                InlineKeyboardButton("✖️ Skipped",  callback_data=f"manual_no_{signal_id}"),
            ]
        ])

        if chat_id and self._app:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception("Failed to send SIGNALS_ONLY alert.")

    async def _async_send_improvement_msg(self, text: str, improvement_id: str) -> None:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return
        chat_id = _get_chat_id()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Undo (24h)", callback_data=f"undo_{improvement_id}")
        ]])
        if chat_id and self._app:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=keyboard
                )
            except Exception:
                logger.exception("Failed to send improvement message.")

    async def _async_send_pause_msg(self, strategy_name: str) -> None:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return
        chat_id = _get_chat_id()
        text = (
            f"⛔ *{strategy_name}* auto-paused.\n"
            f"Win rate < 35% over last 20 trades and 2 improvement attempts failed.\n"
            f"Review performance before resuming."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Unpause", callback_data=f"unpause_{strategy_name}")
        ]])
        if chat_id and self._app:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=keyboard
                )
            except Exception:
                logger.exception("Failed to send pause message.")

    async def _async_send_override_request(
        self, signal: Dict[str, Any], override_details: Dict[str, Any]
    ) -> None:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return

        chat_id   = _get_chat_id()
        signal_id = signal.get("_signal_id", "unknown")
        symbol    = signal.get("symbol", "?")
        entry     = signal.get("entry", signal.get("price", "?"))
        stop      = signal.get("stop_loss", "?")
        t1        = signal.get("target_1", "?")
        conf      = signal.get("confidence", 0)
        conf_pct  = f"{conf*100:.0f}" if isinstance(conf, float) else str(conf)
        why_blocked   = override_details.get("why_blocked", "?")
        why_still_good = override_details.get("why_still_good", "?")

        text = (
            f"🔥 *HIGH CONVICTION SETUP — OVERRIDE REQUEST*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Confidence: {conf_pct}%\n"
            f"📍 {symbol} @ {entry}\n"
            f"🛑 Stop: {stop} | 🎯 Target: {t1}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Why blocked: {why_blocked}\n"
            f"Why it's still good: {why_still_good}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ 90 seconds to respond"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔥 APPROVE OVERRIDE", callback_data=f"override_approve_{signal_id}"),
                InlineKeyboardButton("❌ SKIP",             callback_data=f"override_skip_{signal_id}"),
            ]
        ])

        if chat_id and self._app:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception("Failed to send override request.")


# Alias for import compatibility
TradingTelegramBot = TelegramBot
