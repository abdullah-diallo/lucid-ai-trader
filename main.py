"""
main.py — Lucid AI Trader entry point.
Wraps dashboard/server.py and adds CLI flags:
  --mode paper|live       Trading mode (default: paper)
  --port PORT             Dashboard port (default: 8080)
  --check-only            Verify routes and exit
  --test-tv               Run TradingView integration smoke-test and exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("main")


def _run_tv_test(port: int) -> None:
    """
    TradingView integration smoke-test.
    1. Starts the Flask server in a background thread.
    2. Generates fake ORB_LINES, FVG_ZONE, SIGNAL_ARROW, TRADE_ENTRY drawings.
    3. Calls GET /api/tv/drawings and validates all 4 types are present.
    4. Prints a pass/fail summary.
    """
    import requests

    # ── Populate the drawing queue before the server starts ───────────────────
    from core.drawing_queue import drawing_queue

    drawing_queue.add("ORB_LINES",    {"high": 5510.25, "low": 5498.75})
    drawing_queue.add("FVG_ZONE",     {"top": 5507.50, "bottom": 5505.00,
                                        "type": "BULL", "tf": "5m"})
    drawing_queue.add("SIGNAL_ARROW", {"price": 5511.00, "direction": "UP",
                                        "strategy": "ORB_LONG",
                                        "label": "ORB_LONG 88%"})
    drawing_queue.add("TRADE_ENTRY",  {"price": 5511.00, "stop": 5498.00,
                                        "t1": 5522.50, "t2": 5535.00, "dir": "UP"})

    # ── Start server in background ────────────────────────────────────────────
    os.environ.setdefault("PAPER_MODE", "true")
    os.environ.setdefault("DASHBOARD_PORT", str(port))

    from dashboard.server import socketio, app, _init_systems

    def _serve():
        try:
            _init_systems()
        except Exception as exc:
            log.warning("_init_systems degraded: %s", exc)
        socketio.run(app, host="127.0.0.1", port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    # Wait for server to be ready
    base = f"http://127.0.0.1:{port}"
    for _ in range(20):
        try:
            requests.get(f"{base}/api/tv/status", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("FAIL: server did not start within 10 seconds")
        sys.exit(1)

    # ── Fetch drawings ────────────────────────────────────────────────────────
    resp = requests.get(f"{base}/api/tv/drawings", timeout=5)
    data = resp.json()

    print("\n=== TradingView Integration Test ===")
    print(f"HTTP status:     {resp.status_code}")
    print(f"Drawings count:  {data.get('count', 0)}")
    print("\nPine Script would receive:")
    print(json.dumps(data, indent=2))

    types_returned = {d["type"] for d in data.get("drawings", [])}
    required       = {"ORB_LINES", "FVG_ZONE", "SIGNAL_ARROW", "TRADE_ENTRY"}
    missing        = required - types_returned

    print("\n--- Verification ---")
    for t_name in sorted(required):
        status = "PASS" if t_name in types_returned else "FAIL"
        print(f"  [{status}] {t_name}")

    if missing:
        print(f"\nFAIL: missing drawing types: {missing}")
        sys.exit(1)

    print("\nTradingView integration test passed")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lucid AI Trader")
    parser.add_argument("--mode",       default="paper",
                        choices=["paper", "live"],
                        help="Trading mode")
    parser.add_argument("--port",       type=int,
                        default=int(os.getenv("DASHBOARD_PORT", "8080")),
                        help="Dashboard port")
    parser.add_argument("--check-only", action="store_true",
                        help="Verify routes and exit")
    parser.add_argument("--test-tv",    action="store_true",
                        help="Run TradingView integration smoke-test and exit")
    args = parser.parse_args()

    # Apply paper/live mode to env before importing server
    os.environ["PAPER_MODE"] = "true" if args.mode == "paper" else "false"
    os.environ["DASHBOARD_PORT"] = str(args.port)

    if args.test_tv:
        _run_tv_test(args.port)
        return  # unreachable — _run_tv_test calls sys.exit

    from dashboard.server import app, socketio, _init_systems, get_public_url

    _init_systems()

    if args.check_only:
        routes = sorted(rule.rule for rule in app.url_map.iter_rules())
        print(f"Routes registered: {len(routes)}")
        for r in routes:
            print(f"  {r}")
        print("SocketIO: OK")
        public_url = get_public_url()
        print(f"Webhook URL: {public_url}/api/tv/webhook")
        print("check-only passed")
        sys.exit(0)

    log.info("Starting Lucid AI Trader | mode=%s | port=%s", args.mode, args.port)
    public_url = get_public_url()
    log.info("TradingView webhook URL: %s/api/tv/webhook", public_url)
    log.info("Copy this URL into your TradingView alert settings.")

    socketio.run(app, host="0.0.0.0", port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
