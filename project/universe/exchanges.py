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
    # --- North America ---
    "NYSE": Exchange("NYSE", "New York Stock Exchange", "US", "America/New_York", time(9, 30), time(16, 0)),
    "NASDAQ": Exchange("NASDAQ", "Nasdaq", "US", "America/New_York", time(9, 30), time(16, 0)),
    "AMEX": Exchange("AMEX", "NYSE American", "US", "America/New_York", time(9, 30), time(16, 0)),
    "TSX": Exchange("TSX", "Toronto Stock Exchange", "CA", "America/Toronto", time(9, 30), time(16, 0), suffix=".TO"),
    # --- Nordics ---
    "STO": Exchange("STO", "Nasdaq Stockholm", "SE", "Europe/Stockholm", time(9, 0), time(17, 30), suffix=".ST"),
    "OSL": Exchange("OSL", "Oslo Bors", "NO", "Europe/Oslo", time(9, 0), time(16, 20), suffix=".OL"),
    "CPH": Exchange("CPH", "Nasdaq Copenhagen", "DK", "Europe/Copenhagen", time(9, 0), time(16, 55), suffix=".CO"),
    "HEL": Exchange("HEL", "Nasdaq Helsinki", "FI", "Europe/Helsinki", time(10, 0), time(18, 30), suffix=".HE"),
    # --- Rest of Europe ---
    "FRA": Exchange("FRA", "Deutsche Boerse Xetra", "DE", "Europe/Berlin", time(9, 0), time(17, 30), suffix=".DE"),
    "LSE": Exchange("LSE", "London Stock Exchange", "UK", "Europe/London", time(8, 0), time(16, 30), suffix=".L"),
    # --- Asia-Pacific ---
    "ASX": Exchange("ASX", "Australian Securities Exchange", "AU", "Australia/Sydney", time(10, 0), time(16, 0), suffix=".AX"),
    "NZX": Exchange("NZX", "New Zealand Exchange", "NZ", "Pacific/Auckland", time(10, 0), time(16, 45), suffix=".NZ"),
    "TSE": Exchange("TSE", "Tokyo Stock Exchange", "JP", "Asia/Tokyo", time(9, 0), time(15, 0), suffix=".T"),
    "HKEX": Exchange("HKEX", "Hong Kong Exchange", "HK", "Asia/Hong_Kong", time(9, 30), time(16, 0), suffix=".HK"),
    # --- Round-the-clock / continuous venues ---
    "FOREX": Exchange("FOREX", "FX Interbank (24/5)", "GLOBAL", "UTC", time(0, 0), time(23, 59), suffix="=X"),
    "GLOBEX": Exchange("GLOBEX", "CME Globex Futures (23/5)", "US", "America/Chicago", time(0, 0), time(23, 55), suffix="=F"),
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
