"""Data provider abstraction. Yahoo today, Polygon/Alpaca/IBKR tomorrow — no strategy rewrite."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

log = logging.getLogger(__name__)


@dataclass
class Bars:
    """OHLCV history for a single symbol, oldest bar first."""

    ticker: str
    dates: List[str] = field(default_factory=list)
    opens: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.closes)

    @property
    def last_price(self) -> float:
        return self.closes[-1] if self.closes else 0.0

    def is_usable(self, min_bars: int) -> bool:
        return len(self) >= min_bars and all(c > 0 for c in self.closes[-min_bars:])


class DataProvider(ABC):
    name = "abstract"

    @abstractmethod
    def fetch(self, ticker: str, bars: int, interval: str = "1d") -> Bars:
        """Return history or raise. Retry/blacklist policy lives in ResilientProvider."""


class YahooProvider(DataProvider):
    name = "yahoo"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch(self, ticker: str, bars: int, interval: str = "1d") -> Bars:
        import yfinance as yf  # imported lazily so tests need no network stack

        period_days = max(bars * 2, 30)
        frame = yf.Ticker(ticker).history(period=f"{period_days}d", interval=interval, auto_adjust=True)
        if frame is None or frame.empty:
            raise ValueError(f"No data returned for {ticker}")
        frame = frame.tail(bars)
        return Bars(
            ticker=ticker,
            dates=[str(i.date()) for i in frame.index],
            opens=[float(v) for v in frame["Open"]],
            highs=[float(v) for v in frame["High"]],
            lows=[float(v) for v in frame["Low"]],
            closes=[float(v) for v in frame["Close"]],
            volumes=[float(v) for v in frame["Volume"]],
        )


class ResilientProvider:
    """Wraps any provider with retries, aliasing, blacklisting and hard fault isolation.

    A bad ticker must never take the bot down.
    """

    def __init__(
        self,
        provider: DataProvider,
        max_retries: int = 3,
        backoff_seconds: float = 1.5,
        blacklist_threshold: int = 3,
        aliases: Optional[Dict[str, str]] = None,
        sleep=time.sleep,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.blacklist_threshold = blacklist_threshold
        self.aliases = aliases or {}
        self.failures: Dict[str, int] = defaultdict(int)
        self.blacklist: set[str] = set()
        self._sleep = sleep

    def resolve(self, ticker: str) -> str:
        return self.aliases.get(ticker, ticker)

    def fetch(self, ticker: str, bars: int, interval: str = "1d") -> Optional[Bars]:
        symbol = self.resolve(ticker)
        if symbol in self.blacklist:
            log.debug("Skipping %s — blacklisted after repeated failures", symbol)
            return None

        for attempt in range(1, self.max_retries + 1):
            try:
                data = self.provider.fetch(symbol, bars, interval)
                self.failures.pop(symbol, None)
                return data
            except Exception as exc:  # noqa: BLE001 - isolation is the point
                log.warning("Fetch failed for %s (attempt %s/%s): %s", symbol, attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * attempt)

        self.failures[symbol] += 1
        if self.failures[symbol] >= self.blacklist_threshold:
            self.blacklist.add(symbol)
            log.error("Blacklisting %s after %s consecutive failed scans", symbol, self.failures[symbol])
        return None

    def fetch_many(self, tickers: Sequence[str], bars: int, interval: str = "1d") -> Dict[str, Bars]:
        out: Dict[str, Bars] = {}
        for ticker in tickers:
            data = self.fetch(ticker, bars, interval)
            if data is not None:
                out[ticker] = data
        return out


def build_provider(name: str, timeout: float = 20.0) -> DataProvider:
    if name == "yahoo":
        return YahooProvider(timeout=timeout)
    raise NotImplementedError(
        f"Provider '{name}' not implemented yet. Add a DataProvider subclass — no strategy change required."
    )
