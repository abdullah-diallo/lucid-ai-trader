"""
api/routes_tradingview.py
=========================
Flask Blueprint — TradingView webhook receiver and drawing queue endpoints.

Register in dashboard/server.py:
    from api.routes_tradingview import tv_bp
    app.register_blueprint(tv_bp)
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

from core.drawing_queue import drawing_queue

logger = logging.getLogger(__name__)

tv_bp = Blueprint("tv", __name__)


@tv_bp.route("/api/tv/webhook", methods=["POST"])
def tv_webhook():
    """Receives alerts FROM TradingView Pine Script."""
    data = request.get_json(force=True, silent=True) or {}
    secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
    if secret and data.get("secret") != secret:
        logger.warning("tv_webhook: unauthorized attempt from %s", request.remote_addr)
        return jsonify({"error": "unauthorized"}), 401

    alert_type = data.get("type", "UNKNOWN")
    logger.info("TradingView webhook: type=%s data=%s", alert_type, data)

    # Re-enqueue a SIGNAL_ARROW so the chart reflects inbound TV alerts
    if alert_type == "SIGNAL" and data.get("price"):
        direction = "UP" if str(data.get("dir", "UP")).upper() in ("UP", "LONG", "BUY") else "DOWN"
        drawing_queue.add("SIGNAL_ARROW", {
            "price":     float(data["price"]),
            "direction": direction,
            "strategy":  data.get("strategy", "TV_ALERT"),
            "label":     data.get("label", alert_type),
        })

    return jsonify({"status": "ok"}), 200


@tv_bp.route("/api/tv/drawings", methods=["GET"])
def get_drawings():
    """Pine Script polls this every 5 seconds for new drawings to render."""
    pending = drawing_queue.get_pending()
    return jsonify({"drawings": pending, "count": len(pending)}), 200


@tv_bp.route("/api/tv/clear", methods=["POST"])
def clear_drawings():
    """Dashboard 'Clear All Drawings' button calls this."""
    drawing_queue.clear_all()
    return jsonify({"status": "cleared"}), 200


@tv_bp.route("/api/tv/status", methods=["GET"])
def tv_status():
    """Quick health check — returns pending drawing count."""
    return jsonify({
        "pending_drawings": drawing_queue.pending_count(),
        "webhook_secret_set": bool(os.getenv("TRADINGVIEW_WEBHOOK_SECRET")),
    }), 200
