"""Universe definitions live outside the strategy. Swap or extend without touching logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Symbol:
    ticker: str
    exchange: str
    country: str
    sector: str = "Unknown"
    name: str = ""

    def provider_ticker(self, suffix: str = "") -> str:
        return f"{self.ticker}{suffix}" if suffix and not self.ticker.endswith(suffix) else self.ticker


@dataclass
class Universe:
    key: str
    label: str
    exchange: str
    symbols: List[Symbol] = field(default_factory=list)

    def tickers(self) -> List[str]:
        return [s.ticker for s in self.symbols]


def _mk(exchange: str, country: str, rows: List[tuple]) -> List[Symbol]:
    return [Symbol(t, exchange, country, sector, name) for t, sector, name in rows]


# Trimmed representative membership; production loads full constituents from
# config/universes/*.csv or a provider endpoint via load_universe(refresh=True).
UNIVERSES: Dict[str, Universe] = {
    "SP500": Universe("SP500", "S&P 500", "NYSE", _mk("NYSE", "US", [
        ("AAPL", "Technology", "Apple"), ("MSFT", "Technology", "Microsoft"),
        ("NVDA", "Technology", "NVIDIA"), ("JPM", "Financials", "JPMorgan"),
        ("XOM", "Energy", "Exxon Mobil"), ("UNH", "Healthcare", "UnitedHealth"),
        ("CAT", "Industrials", "Caterpillar"), ("PG", "Staples", "Procter & Gamble"),
    ])),
    "NASDAQ100": Universe("NASDAQ100", "Nasdaq 100", "NASDAQ", _mk("NASDAQ", "US", [
        ("AMD", "Technology", "AMD"), ("TSLA", "Consumer", "Tesla"),
        ("AVGO", "Technology", "Broadcom"), ("COST", "Staples", "Costco"),
        ("PANW", "Technology", "Palo Alto Networks"),
    ])),
    "TSX60": Universe("TSX60", "TSX 60", "TSX", _mk("TSX", "CA", [
        ("SHOP", "Technology", "Shopify"), ("ENB", "Energy", "Enbridge"),
        ("RY", "Financials", "Royal Bank of Canada"), ("CNQ", "Energy", "Canadian Natural"),
    ])),
    "ASX200": Universe("ASX200", "ASX 200", "ASX", _mk("ASX", "AU", [
        ("BHP", "Materials", "BHP Group"), ("CBA", "Financials", "Commonwealth Bank"),
        ("CSL", "Healthcare", "CSL Limited"), ("WES", "Consumer", "Wesfarmers"),
    ])),
    "NZX50": Universe("NZX50", "NZX 50", "NZX", _mk("NZX", "NZ", [
        ("AIR", "Industrials", "Air New Zealand"), ("FPH", "Healthcare", "Fisher & Paykel"),
    ])),
    "FTSE100": Universe("FTSE100", "FTSE 100", "LSE", _mk("LSE", "UK", [
        ("SHEL", "Energy", "Shell"), ("AZN", "Healthcare", "AstraZeneca"),
        ("HSBA", "Financials", "HSBC"),
    ])),
    "CRYPTO": Universe("CRYPTO", "Crypto Majors", "CRYPTO", _mk("CRYPTO", "GLOBAL", [
        ("BTC-USD", "Crypto", "Bitcoin"), ("ETH-USD", "Crypto", "Ethereum"),
        ("SOL-USD", "Crypto", "Solana"), ("LINK-USD", "Crypto", "Chainlink"),
    ])),
}


def get_universe(key: str) -> Universe:
    if key not in UNIVERSES:
        raise KeyError(f"Unknown universe '{key}'. Known: {sorted(UNIVERSES)}")
    return UNIVERSES[key]


def universes_for_exchanges(codes: List[str]) -> List[Universe]:
    return [u for u in UNIVERSES.values() if u.exchange in codes]


def find_symbol(ticker: str) -> Optional[Symbol]:
    for universe in UNIVERSES.values():
        for symbol in universe.symbols:
            if symbol.ticker == ticker:
                return symbol
    return None
