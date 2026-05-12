"""
session_manager.py
==================
Market session and trade-window logic for US index futures workflows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class EconomicEvent:
    """
    Structured event used by is_news_window() checks.
    """

    name: str
    timestamp: datetime


class SessionManager:
    """
    Session and timing manager for futures trading logic.

    Sessions tracked in US/Eastern:
    - Globex
    - Pre-market
    - RTH (Regular Trading Hours)
    - AH (After Hours)
    """

    HIGH_VOLUME_WINDOWS: Tuple[Tuple[time, time], ...] = (
        (time(9, 30), time(11, 30)),
        (time(14, 0), time(16, 0)),
    )

    def __init__(self) -> None:
        self.tz = ET
        self.news_window_minutes = 30

    def get_current_session(self, now: Optional[datetime] = None) -> str:
        """
        Return the current session name.
        """
        dt = self._normalize_now(now)
        if self._is_weekend_closed(dt):
            return "Closed"

        t = dt.time()
        if time(9, 30) <= t < time(16, 0):
            return "RTH"
        if time(4, 0) <= t < time(9, 30):
            return "Pre-market"
        if time(16, 0) <= t < time(20, 0):
            return "AH"
        if t >= time(20, 0) or t < time(4, 0):
            return "Globex"

        return "Closed"

    def is_high_volume_time(self, now: Optional[datetime] = None) -> bool:
        """
        True during 9:30-11:30 ET and 14:00-16:00 ET.
        """
        dt = self._normalize_now(now)
        if self._is_weekend_closed(dt):
            return False

        current = dt.time()
        return any(start <= current < end for start, end in self.HIGH_VOLUME_WINDOWS)

    def is_news_window(self, now: Optional[datetime] = None) -> bool:
        """
        True if current time is within +/- 30 minutes of a scheduled event.
        Events include recurring FOMC, CPI, PPI, and NFP placeholders.
        """
        dt = self._normalize_now(now)
        events = self._events_for_date(dt.date())
        delta = timedelta(minutes=self.news_window_minutes)

        for event in events:
            if abs(event.timestamp - dt) <= delta:
                logger.info("News window active near event: %s at %s", event.name, event.timestamp.isoformat())
                return True

        return False

    def should_trade_now(self, now: Optional[datetime] = None) -> bool:
        """
        Main trade gate. Conservative default:
        - Weekday only
        - RTH only
        - During high-volume windows
        - Not inside news windows
        """
        dt = self._normalize_now(now)
        if self._is_weekend_closed(dt):
            return False

        session = self.get_current_session(dt)
        if session != "RTH":
            return False

        if not self.is_high_volume_time(dt):
            return False

        if self.is_news_window(dt):
            return False

        return True

    def time_until_next_session(self, now: Optional[datetime] = None) -> timedelta:
        """
        Return time delta until the next session boundary.
        """
        dt = self._normalize_now(now)
        next_change = self._next_session_boundary(dt)
        return next_change - dt

    def _normalize_now(self, now: Optional[datetime]) -> datetime:
        """
        Ensure datetime is timezone-aware and normalized to ET.
        """
        if now is None:
            return datetime.now(self.tz)
        if now.tzinfo is None:
            return now.replace(tzinfo=self.tz)
        return now.astimezone(self.tz)

    def _is_weekend_closed(self, dt: datetime) -> bool:
        """
        Futures typically close from Friday 17:00 ET to Sunday 18:00 ET.
        """
        wd = dt.weekday()  # Monday=0 ... Sunday=6
        t = dt.time()
        if wd == 5:
            return True
        if wd == 4 and t >= time(17, 0):
            return True
        if wd == 6 and t < time(18, 0):
            return True
        return False

    def _next_session_boundary(self, dt: datetime) -> datetime:
        """
        Find next session boundary for countdown displays.
        """
        candidates = []
        for boundary_time in (time(4, 0), time(9, 30), time(16, 0), time(20, 0), time(17, 0), time(18, 0)):
            candidate = datetime.combine(dt.date(), boundary_time, tzinfo=self.tz)
            if candidate > dt:
                candidates.append(candidate)

        day = dt + timedelta(days=1)
        for boundary_time in (time(4, 0), time(9, 30), time(16, 0), time(20, 0), time(17, 0), time(18, 0)):
            candidates.append(datetime.combine(day.date(), boundary_time, tzinfo=self.tz))

        candidates.sort()
        for candidate in candidates:
            if self._is_real_boundary(candidate):
                return candidate

        # Defensive fallback.
        return dt + timedelta(hours=1)

    def _is_real_boundary(self, dt: datetime) -> bool:
        """
        Filter out boundaries that occur during known weekend closure windows.
        """
        before = dt - timedelta(seconds=1)
        return self.get_current_session(before) != self.get_current_session(dt)

    def _events_for_date(self, d: date) -> List[EconomicEvent]:
        """
        Build recurring event schedule for one date.

        Recurring assumptions:
        - CPI: second Tuesday, 08:30 ET
        - PPI: second Thursday, 08:30 ET
        - NFP: first Friday, 08:30 ET
        - FOMC: third Wednesday of Jan/Mar/May/Jun/Jul/Sep/Nov/Dec, 14:00 ET
        """
        events: List[EconomicEvent] = []

        if d == self._nth_weekday_of_month(d.year, d.month, weekday=1, n=2):  # Tuesday
            events.append(EconomicEvent("CPI Release", datetime.combine(d, time(8, 30), tzinfo=self.tz)))

        if d == self._nth_weekday_of_month(d.year, d.month, weekday=3, n=2):  # Thursday
            events.append(EconomicEvent("PPI Release", datetime.combine(d, time(8, 30), tzinfo=self.tz)))

        if d == self._nth_weekday_of_month(d.year, d.month, weekday=4, n=1):  # Friday
            events.append(EconomicEvent("NFP Release", datetime.combine(d, time(8, 30), tzinfo=self.tz)))

        fomc_months = {1, 3, 5, 6, 7, 9, 11, 12}
        if d.month in fomc_months and d == self._nth_weekday_of_month(d.year, d.month, weekday=2, n=3):  # Wednesday
            events.append(EconomicEvent("FOMC Rate Decision", datetime.combine(d, time(14, 0), tzinfo=self.tz)))

        return events

    @staticmethod
    def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
        """
        Return the date of the nth weekday in a month.
        weekday: Monday=0 ... Sunday=6
        """
        first = date(year, month, 1)
        first_delta = (weekday - first.weekday()) % 7
        day_num = 1 + first_delta + (n - 1) * 7
        return date(year, month, day_num)
