"""
core/self_improvement_engine.py
================================
Analyzes strategy performance and proposes/applies improvements using Groq.
Runs a weekly review every Sunday midnight via the `schedule` library.

Filter categories stored in strategy_configs.config_json:
  {"filters": [{"type": "TIME_FILTER", "start": "12:00", "end": "14:00"}, ...]}
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from data.supabase_client import get_supabase

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).parent.parent / "logs"
IMPROVEMENT_HISTORY_FILE = LOGS_DIR / "improvement_history.json"

MIN_TRADES = {"analyze": 15, "auto_apply": 20, "auto_pause": 20}

FILTER_CATEGORIES = [
    "TIME_FILTER",         # params: start (HH:MM), end (HH:MM)
    "SESSION_FILTER",      # params: allowed_sessions list
    "HTF_FILTER",          # params: required_bias ("BULLISH"/"BEARISH"/"AGREE")
    "NEWS_FILTER",         # params: min_minutes_from_news int
    "CONFIDENCE_BOOST",    # params: new_threshold float
    "CONFLUENCE_REQUIRE",  # params: required_factors list
    "VWAP_FILTER",         # params: position ("ABOVE"/"BELOW"/"EITHER")
    "RANGE_FILTER",        # params: block_when_ranging bool
]


class SelfImprovementEngine:
    """
    Weekly self-review + auto-improvement of underperforming strategies.

    Inject dependencies after construction:
        engine.set_telegram_bot(bot)
    """

    def __init__(self, performance_engine) -> None:
        self._performance_engine = performance_engine
        self._telegram_bot = None
        self._scheduler_thread: Optional[threading.Thread] = None
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def set_telegram_bot(self, bot) -> None:
        self._telegram_bot = bot

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def start_scheduler(self) -> None:
        """Launch weekly review scheduler in a daemon thread."""
        try:
            import schedule as _schedule
        except ImportError:
            logger.warning("schedule library not installed — weekly review disabled.")
            return

        def _run():
            _schedule.every().sunday.at("00:00").do(self.run_weekly_review)
            while True:
                _schedule.run_pending()
                time.sleep(60)

        self._scheduler_thread = threading.Thread(
            target=_run, daemon=True, name="self-improvement-scheduler"
        )
        self._scheduler_thread.start()
        logger.info("Self-improvement scheduler started (weekly review: Sunday 00:00).")

    # ── Weekly review ─────────────────────────────────────────────────────────

    def run_weekly_review(
        self,
        user_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyze last week's trades, propose improvements for underperformers.
        Pass dry_run=True to print proposals without applying anything.
        """
        logger.info("Running weekly self-improvement review%s…", " (DRY-RUN)" if dry_run else "")
        pe = self._performance_engine
        all_stats = pe.get_all_strategies_report("week", user_id)

        improved: List[str] = []
        paused:   List[str] = []
        reviewed = 0

        for stats in all_stats:
            strategy_name = stats["strategy_name"]
            total = stats.get("total_trades", 0)

            # Step 5.1: minimum sample size guard
            if total < MIN_TRADES["analyze"]:
                logger.info(
                    "Skipping %s: only %d trades (need %d)",
                    strategy_name, total, MIN_TRADES["analyze"],
                )
                continue

            reviewed += 1

            # Only analyze underperforming strategies
            if stats.get("win_rate_pct", 100) >= 50:
                continue

            losing = self._fetch_losing_trades(strategy_name, "week", user_id)
            if not losing:
                continue

            proposal = self.analyze_losing_trades(strategy_name, losing)
            if not proposal:
                continue

            if dry_run:
                print(f"\n[DRY-RUN] {strategy_name} ({total} trades, {stats['win_rate_pct']}% WR):")
                print(json.dumps(proposal, indent=2))
                continue

            if total >= MIN_TRADES["auto_pause"] and self.check_auto_pause(strategy_name, stats, user_id):
                paused.append(strategy_name)
            elif total >= MIN_TRADES["auto_apply"] and self.apply_improvement(
                strategy_name, proposal, stats, user_id, len(losing)
            ):
                improved.append(strategy_name)

        # Evaluate effectiveness of past improvements
        if not dry_run:
            self.evaluate_improvements(user_id)

        summary = {
            "strategies_reviewed": reviewed,
            "improved":  improved,
            "paused":    paused,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if not dry_run and self._telegram_bot:
            self._send_weekly_report(all_stats, improved, paused)

        return summary

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze_losing_trades(
        self, strategy_name: str, losing_trades: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Send losing trades to Groq and get a structured improvement proposal.
        Returns None if analysis fails or no pattern found.
        """
        from ai.groq_client import DEFAULT_MODEL, get_groq

        if not losing_trades:
            return None

        sample = losing_trades[:20]
        filter_list = "\n".join(f"  - {f}" for f in FILTER_CATEGORIES)
        prompt = f"""You are analyzing why the {strategy_name} strategy has been underperforming.

Here are the last {len(sample)} losing trades (JSON):
{json.dumps(sample, indent=2, default=str)}

Identify:
1. What CONDITIONS were consistently present in losing trades?
2. What specific FILTER RULE would have avoided most losses?
3. What PARAMETER ADJUSTMENT would improve performance?

You MUST choose filter_type from this exact list:
{filter_list}

Parameter schemas by type:
  TIME_FILTER         → {{"start": "HH:MM", "end": "HH:MM"}}
  SESSION_FILTER      → {{"allowed_sessions": ["RTH", "Pre-market", ...]}}
  HTF_FILTER          → {{"required_bias": "BULLISH"|"BEARISH"|"AGREE"}}
  NEWS_FILTER         → {{"min_minutes_from_news": <int>}}
  CONFIDENCE_BOOST    → {{"new_threshold": <float 0.0-1.0>}}
  CONFLUENCE_REQUIRE  → {{"required_factors": ["factor1", ...]}}
  VWAP_FILTER         → {{"position": "ABOVE"|"BELOW"|"EITHER"}}
  RANGE_FILTER        → {{"block_when_ranging": true|false}}

Respond ONLY with this JSON (no markdown, no explanation):
{{
  "pattern_found": "<description of the losing pattern>",
  "proposed_filter": "<specific rule in plain English>",
  "filter_type": "<one of the filter types above>",
  "filter_params": {{<type-specific params>}},
  "expected_improvement_pct": <integer>,
  "confidence_in_fix": <float 0.0-1.0>
}}"""

        try:
            client = get_groq()
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a quantitative trading analyst. Respond ONLY with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            import re as _re
            raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.MULTILINE)
            raw = _re.sub(r"\s*```$", "", raw, flags=_re.MULTILINE)
            proposal = json.loads(raw.strip())
            # Validate filter_type; fall back gracefully
            if proposal.get("filter_type") not in FILTER_CATEGORIES:
                proposal["filter_type"] = "CONFIDENCE_BOOST"
                proposal.setdefault("filter_params", {"new_threshold": 0.75})
            return proposal
        except Exception:
            logger.exception("analyze_losing_trades: Groq call failed for %s.", strategy_name)
            return None

    # ── Apply improvement ─────────────────────────────────────────────────────

    def apply_improvement(
        self,
        strategy_name: str,
        proposal: Dict[str, Any],
        stats: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        trades_analyzed: int = 0,
    ) -> bool:
        """
        If confidence_in_fix > 0.70: write filter to strategy_configs,
        append to logs/improvement_history.json, send Telegram with [Undo].
        """
        confidence = float(proposal.get("confidence_in_fix", 0.0))
        if confidence <= 0.70:
            logger.info(
                "Improvement confidence %.2f ≤ 0.70 for %s — not applying.",
                confidence, strategy_name,
            )
            return False

        improvement_id = str(uuid.uuid4())
        win_rate_before = (stats or {}).get("win_rate_pct", 0) / 100.0

        sb = get_supabase()
        try:
            # Build structured filter using FILTER_CATEGORIES schema
            new_filter = {
                "type":   proposal.get("filter_type", "CONFIDENCE_BOOST"),
                "params": proposal.get("filter_params", {}),
                "note":   proposal.get("proposed_filter", ""),
            }

            # Read/update Supabase strategy_configs
            query = sb.table("strategy_configs").select("id, config_json").eq("strategy_id", strategy_name)
            if user_id:
                query = query.eq("user_id", user_id)
            res = query.limit(1).execute()

            if res.data:
                row     = res.data[0]
                config  = row.get("config_json") or {}
                filters = config.get("filters", [])
                filters.append(new_filter)
                config["filters"] = filters
                sb.table("strategy_configs").update({"config_json": config}).eq("id", row["id"]).execute()
            else:
                insert_data: Dict[str, Any] = {
                    "strategy_id": strategy_name,
                    "enabled":     True,
                    "config_json": {"filters": [new_filter]},
                }
                if user_id:
                    insert_data["user_id"] = user_id
                sb.table("strategy_configs").insert(insert_data).execute()

            # Log to Supabase improvement_history
            hist_data: Dict[str, Any] = {
                "id":            improvement_id,
                "strategy_name": strategy_name,
                "proposal_json": proposal,
            }
            if user_id:
                hist_data["user_id"] = user_id
            sb.table("improvement_history").insert(hist_data).execute()

            # Step 5.3: append to local logs/improvement_history.json
            filter_applied: Dict[str, Any] = {
                "type": proposal.get("filter_type", "CONFIDENCE_BOOST"),
                **proposal.get("filter_params", {}),
            }
            self._append_improvement_entry({
                "id":                       improvement_id,
                "timestamp":                datetime.now(timezone.utc).isoformat(),
                "strategy":                 strategy_name,
                "problem":                  proposal.get("pattern_found", ""),
                "filter_applied":           filter_applied,
                "trades_analyzed":          trades_analyzed,
                "expected_improvement_pct": int(proposal.get("expected_improvement_pct", 0)),
                "confidence_in_fix":        round(confidence, 4),
                "win_rate_before":          round(win_rate_before, 4),
                "win_rate_after":           None,
                "status":                   "ACTIVE",
                "applied_by":               "auto",
                "can_undo":                 True,
            })

            logger.info("Applied improvement to %s: %s", strategy_name, proposal.get("proposed_filter"))

            if self._telegram_bot:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                text = (
                    f"📊 *{strategy_name} improved*\n"
                    f"Filter: {proposal.get('proposed_filter', '?')}\n"
                    f"Expected improvement: +{proposal.get('expected_improvement_pct', '?')}%\n"
                    f"Confidence: {confidence:.0%}"
                )
                self._telegram_bot._send_nowait(
                    self._telegram_bot._async_send_improvement_msg(text, improvement_id)
                )

            return True
        except Exception:
            logger.exception("Failed to apply improvement for %s.", strategy_name)
            return False

    def revert_improvement(self, improvement_id: str) -> bool:
        """Revert an applied improvement (remove the last filter added)."""
        sb = get_supabase()
        try:
            res = sb.table("improvement_history").select("*").eq("id", improvement_id).single().execute()
            if not res.data:
                return False
            record = res.data
            strategy_name = record["strategy_name"]
            user_id = record.get("user_id")

            # Remove last filter from strategy_configs
            query = sb.table("strategy_configs").select("id, config_json").eq("strategy_id", strategy_name)
            if user_id:
                query = query.eq("user_id", user_id)
            cfg_res = query.limit(1).execute()

            if cfg_res.data:
                row     = cfg_res.data[0]
                config  = row.get("config_json") or {}
                filters = config.get("filters", [])
                if filters:
                    filters.pop()
                config["filters"] = filters
                sb.table("strategy_configs").update({"config_json": config}).eq("id", row["id"]).execute()

            # Mark reverted in Supabase
            sb.table("improvement_history").update({
                "reverted_at":    datetime.now(timezone.utc).isoformat(),
                "was_successful": False,
            }).eq("id", improvement_id).execute()

            # Step 5.3: update local JSON file status to UNDONE
            self._update_improvement_status(improvement_id, "UNDONE")

            logger.info("Reverted improvement %s for %s.", improvement_id, strategy_name)

            if self._telegram_bot:
                self._telegram_bot.send_message(
                    f"↩️ Filter removed from {strategy_name}. Reverted."
                )

            return True
        except Exception:
            logger.exception("Failed to revert improvement %s.", improvement_id)
            return False

    # ── Evaluate improvement effectiveness ────────────────────────────────────

    def evaluate_improvements(self, user_id: Optional[str] = None) -> None:
        """
        Step 5.4: Check effectiveness of ACTIVE improvements.
        Runs as part of run_weekly_review.
        """
        history = self._load_improvement_history()
        changed = False

        for improvement in history.get("improvements", []):
            if improvement.get("status") != "ACTIVE":
                continue

            strategy = improvement["strategy"]
            trades_since = self._get_trades_since(strategy, improvement["timestamp"], user_id)
            if len(trades_since) < 20:
                continue

            new_win_rate = (
                sum(1 for t in trades_since if float(t.get("pnl", 0)) > 0) / len(trades_since)
            )
            improvement["win_rate_after"] = round(new_win_rate, 4)
            win_rate_before = improvement.get("win_rate_before", 0)

            if new_win_rate >= win_rate_before + 0.05:
                improvement["status"] = "SUCCESSFUL"
                logger.info(
                    "Improvement SUCCESSFUL for %s: WR %.0f%% → %.0f%%",
                    strategy, win_rate_before * 100, new_win_rate * 100,
                )
            else:
                improvement["status"] = "INEFFECTIVE"
                failed_count = sum(
                    1 for imp in history.get("improvements", [])
                    if imp.get("strategy") == strategy and imp.get("status") == "INEFFECTIVE"
                )
                logger.info(
                    "Improvement INEFFECTIVE for %s (%d total failed attempts).",
                    strategy, failed_count,
                )
                if failed_count >= 2:
                    self._pause_strategy(
                        strategy, "2 improvement attempts failed", user_id
                    )
                    if self._telegram_bot:
                        self._telegram_bot.send_message(
                            f"⛔ {strategy} auto-paused after 2 ineffective improvement attempts."
                        )
            changed = True

        if changed:
            self._save_improvement_history(history)

    # ── Auto pause ────────────────────────────────────────────────────────────

    def check_auto_pause(
        self,
        strategy_name: str,
        strategy_stats: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Pause strategy if win_rate < 35% AND ≥ 2 failed improvement attempts.
        Returns True if paused.
        """
        if strategy_stats.get("win_rate_pct", 100) >= 35:
            return False

        sb = get_supabase()
        try:
            query = sb.table("improvement_history").select("id").eq("strategy_name", strategy_name)
            if user_id:
                query = query.eq("user_id", user_id)
            query = query.is_("reverted_at", "null")
            res = query.execute()
            attempt_count = len(res.data or [])
        except Exception:
            attempt_count = 0

        if attempt_count < 2:
            return False

        return self._pause_strategy(
            strategy_name, "win_rate<35%, 2 failed improvements", user_id
        )

    def _pause_strategy(
        self, strategy_name: str, reason: str, user_id: Optional[str] = None
    ) -> bool:
        """Disable a strategy in Supabase and notify via Telegram with [Unpause]."""
        sb = get_supabase()
        try:
            query = sb.table("strategy_configs").select("id").eq("strategy_id", strategy_name)
            if user_id:
                query = query.eq("user_id", user_id)
            cfg_res = query.limit(1).execute()
            if cfg_res.data:
                sb.table("strategy_configs").update({"enabled": False}).eq("id", cfg_res.data[0]["id"]).execute()
            else:
                insert_data: Dict[str, Any] = {"strategy_id": strategy_name, "enabled": False}
                if user_id:
                    insert_data["user_id"] = user_id
                sb.table("strategy_configs").insert(insert_data).execute()
        except Exception:
            logger.exception("Failed to pause strategy %s.", strategy_name)
            return False

        logger.info("Auto-paused strategy %s: %s", strategy_name, reason)

        if self._telegram_bot:
            self._telegram_bot._send_nowait(
                self._telegram_bot._async_send_pause_msg(strategy_name)
            )

        return True

    def unpause_strategy(self, strategy_name: str, user_id: Optional[str] = None) -> bool:
        """Re-enable a paused strategy."""
        sb = get_supabase()
        try:
            query = sb.table("strategy_configs").select("id").eq("strategy_id", strategy_name)
            if user_id:
                query = query.eq("user_id", user_id)
            cfg_res = query.limit(1).execute()
            if cfg_res.data:
                sb.table("strategy_configs").update({"enabled": True}).eq("id", cfg_res.data[0]["id"]).execute()
                return True
        except Exception:
            logger.exception("Failed to unpause %s.", strategy_name)
        return False

    def suggest_new_strategy(self, observed_patterns: List[Dict[str, Any]]) -> None:
        """Log and notify — no auto-application in v1."""
        if not observed_patterns:
            return
        desc = observed_patterns[0].get("description", "Unnamed pattern")
        logger.info("New pattern observed: %s", desc)
        if self._telegram_bot:
            self._telegram_bot.send_message(
                f"🆕 New trading pattern observed:\n{desc}\n\n"
                "To test this pattern, it must be implemented and approved manually."
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_losing_trades(
        self, strategy_name: str, date_range: str, user_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        sb = get_supabase()
        from core.performance_engine import _date_filter
        try:
            query = (
                sb.table("trades")
                .select("*")
                .eq("status", "closed")
                .eq("strategy_name", strategy_name)
            )
            if user_id:
                query = query.eq("user_id", user_id)
            gte, lte = _date_filter(date_range)
            if gte:
                query = query.gte("closed_at", gte)
            res = query.execute()
            return [t for t in (res.data or []) if float(t.get("pnl", 0)) <= 0]
        except Exception:
            logger.exception("Failed to fetch losing trades for %s.", strategy_name)
            return []

    def _get_trades_since(
        self, strategy_name: str, since_iso: str, user_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Fetch all closed trades for strategy_name at or after since_iso."""
        sb = get_supabase()
        try:
            query = (
                sb.table("trades")
                .select("pnl, closed_at")
                .eq("status", "closed")
                .eq("strategy_name", strategy_name)
                .gte("closed_at", since_iso)
            )
            if user_id:
                query = query.eq("user_id", user_id)
            res = query.order("closed_at", desc=False).execute()
            return res.data or []
        except Exception:
            logger.exception("Failed to fetch trades since %s for %s.", since_iso, strategy_name)
            return []

    # ── JSON history file helpers ─────────────────────────────────────────────

    def _load_improvement_history(self) -> Dict[str, Any]:
        if IMPROVEMENT_HISTORY_FILE.exists():
            try:
                return json.loads(IMPROVEMENT_HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Failed to read improvement_history.json — starting fresh.")
        return {"improvements": []}

    def _save_improvement_history(self, history: Dict[str, Any]) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        IMPROVEMENT_HISTORY_FILE.write_text(
            json.dumps(history, indent=2, default=str),
            encoding="utf-8",
        )

    def _append_improvement_entry(self, entry: Dict[str, Any]) -> None:
        history = self._load_improvement_history()
        history.setdefault("improvements", []).append(entry)
        self._save_improvement_history(history)

    def _update_improvement_status(self, improvement_id: str, status: str, **extra: Any) -> None:
        history = self._load_improvement_history()
        for imp in history.get("improvements", []):
            if imp.get("id") == improvement_id:
                imp["status"] = status
                imp.update(extra)
                break
        self._save_improvement_history(history)

    def _send_weekly_report(
        self,
        all_stats: List[Dict[str, Any]],
        improved: List[str],
        paused: List[str],
    ) -> None:
        pe   = self._performance_engine
        text = pe.format_all_strategies_telegram(all_stats, "week")
        if improved:
            text += f"\n\n✅ Improved this week: {', '.join(improved)}"
        if paused:
            text += f"\n\n⛔ Auto-paused this week: {', '.join(paused)}"
        self._telegram_bot.send_message(text)


# ── CLI dry-run entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Self-improvement engine CLI")
    parser.add_argument("--dry-run", action="store_true", help="Print proposals without applying anything")
    args = parser.parse_args()

    from core.performance_engine import StrategyPerformanceEngine

    pe = StrategyPerformanceEngine()
    engine = SelfImprovementEngine(pe)

    print("Loading trade history and analyzing underperforming strategies…")
    summary = engine.run_weekly_review(dry_run=args.dry_run)

    print("\n── Summary ──────────────────────────────────────────────")
    print(f"Strategies reviewed : {summary['strategies_reviewed']}")
    if not args.dry_run:
        print(f"Improved            : {summary.get('improved', [])}")
        print(f"Paused              : {summary.get('paused', [])}")
    else:
        print("(DRY-RUN: no changes applied)")
