"""
core/drawing_queue.py
=====================
Thread-safe in-memory queue for drawings sent from the AI to TradingView.
Pine Script polls /api/tv/drawings every 5 seconds to consume pending items.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List


class DrawingQueue:
    """
    Thread-safe queue of drawing commands.
    Producers call add(); the Pine Script poll endpoint calls get_pending().

    Drawing types:
      FVG_ZONE:     {"top": float, "bottom": float, "type": "BULL"|"BEAR", "tf": str}
      ORDER_BLOCK:  {"high": float, "low": float, "type": "BULL"|"BEAR"}
      ORB_LINES:    {"high": float, "low": float}
      SIGNAL_ARROW: {"price": float, "direction": "UP"|"DOWN", "strategy": str, "label": str}
      TRADE_ENTRY:  {"price": float, "stop": float, "t1": float, "t2": float, "dir": str}
      LEVEL_LINE:   {"price": float, "label": str, "style": "solid"|"dashed"}
      BOS_LABEL:    {"price": float, "label": "BOS"|"CHoCH"|"MSS"}
      KILL_ZONE:    {"session": str}
      CLEAR_ALL:    {}
    """

    def __init__(self) -> None:
        self._queue: List[Dict[str, Any]] = []
        self._lock = Lock()

    def add(self, drawing_type: str, params: Dict[str, Any]) -> str:
        """Enqueue a drawing command. Returns its UUID."""
        drawing = {
            "id":        str(uuid.uuid4()),
            "type":      drawing_type,
            "params":    params,
            "timestamp": datetime.utcnow().isoformat(),
            "delivered": False,
        }
        with self._lock:
            self._queue.append(drawing)
        return drawing["id"]

    def get_pending(self) -> List[Dict[str, Any]]:
        """
        Return all undelivered drawings and mark them delivered.
        Idempotent for the same poll cycle — duplicates never re-appear.
        """
        with self._lock:
            pending = [d.copy() for d in self._queue if not d["delivered"]]
            for d in self._queue:
                if not d["delivered"]:
                    d["delivered"] = True
        return pending

    def clear_all(self) -> None:
        """Flush the queue and enqueue a CLEAR_ALL sentinel for Pine Script."""
        with self._lock:
            self._queue = []
        self.add("CLEAR_ALL", {})

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for d in self._queue if not d["delivered"])


# Module-level singleton — import this everywhere
drawing_queue = DrawingQueue()
