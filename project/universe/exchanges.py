"""Exchange session calendar. Never scan a closed market."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Exchange:
    code: str
    name: str
    country: str
    timezone: str
    open_time: time
    close_time: time
    weekdays: tuple = (0, 1, 2, 3, 4)
    always_open: bool = False
    suffix: str = ""          # Yahoo ticker suffix, e.g. ".TO", ".AX"

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.timezone))

    def is_open(self, at: Optional[datetime] = None) -> bool:
        if self.always_open:
            return True
        moment = (at or datetime.now(ZoneInfo(self.timezone))).astimezone(ZoneInfo(self.timezone))
        if moment.weekday() not in self.weekdays:
            return False
        return self.open_time <= moment.time() <= self.close_time

    def next_open(self, at: Optional[datetime] = None) -> datetime:
        tz = ZoneInfo(self.timezone)
        moment = (at or datetime.now(tz)).astimezone(tz)
        if self.always_open:
            return moment
        for day_offset in range(0, 8):
            candidate_day = (moment + timedelta(days=day_offset)).date()
            candidate = datetime.combine(candidate_day, self.open_time, tzinfo=tz)
            if candidate.weekday() in self.weekdays and candidate > moment:
                return candidate
        return moment + timedelta(days=1)

    def opens_within(self, minutes: int, at: Optional[datetime] = None) -> bool:
        if self.always_open:
            return False
        tz = ZoneInfo(self.timezone)
        moment = (at or datetime.now(tz)).astimezone(tz)
        return timedelta(0) < (self.next_open(moment) - moment) <= timedelta(minutes=minutes)


EXCHANGES: Dict[str, Exchange] = {
    "NYSE": Exchange("NYSE", "New York Stock Exchange", "US", "America/New_York", time(9, 30), time(16, 0)),
    "NASDAQ": Exchange("NASDAQ", "Nasdaq", "US", "America/New_York", time(9, 30), time(16, 0)),
    "AMEX": Exchange("AMEX", "NYSE American", "US", "America/New_York", time(9, 30), time(16, 0)),
    "TSX": Exchange("TSX", "Toronto Stock Exchange", "CA", "America/Toronto", time(9, 30), time(16, 0), suffix=".TO"),
    "ASX": Exchange("ASX", "Australian Securities Exchange", "AU", "Australia/Sydney", time(10, 0), time(16, 0), suffix=".AX"),
    "NZX": Exchange("NZX", "New Zealand Exchange", "NZ", "Pacific/Auckland", time(10, 0), time(16, 45), suffix=".NZ"),
    "LSE": Exchange("LSE", "London Stock Exchange", "UK", "Europe/London", time(8, 0), time(16, 30), suffix=".L"),
    "CRYPTO": Exchange("CRYPTO", "Crypto (24/7)", "GLOBAL", "UTC", time(0, 0), time(23, 59), weekdays=(0, 1, 2, 3, 4, 5, 6), always_open=True),
}


def open_exchanges(at: Optional[datetime] = None) -> List[Exchange]:
    return [ex for ex in EXCHANGES.values() if ex.is_open(at)]


def opening_soon(minutes: int = 30, at: Optional[datetime] = None) -> List[Exchange]:
    return [ex for ex in EXCHANGES.values() if ex.opens_within(minutes, at)]


def closed_exchanges(at: Optional[datetime] = None) -> List[Exchange]:
    return [ex for ex in EXCHANGES.values() if not ex.is_open(at)]


def seconds_until_next_open(at: Optional[datetime] = None) -> float:
    """How long the bot may sleep when everything is shut."""
    if open_exchanges(at):
        return 0.0
    now = at or datetime.now(ZoneInfo("UTC"))
    waits = [(ex.next_open(now) - now.astimezone(ZoneInfo(ex.timezone))).total_seconds() for ex in EXCHANGES.values()]
    return max(0.0, min(waits))
