"""Risk gates and position sizing. Risk always wins over profit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from project.config.settings import RiskConfig


@dataclass
class OpenPosition:
    ticker: str
    sector: str
    country: str
    shares: float
    entry: float
    stop: float

    @property
    def market_value(self) -> float:
        return self.shares * self.entry

    @property
    def open_risk(self) -> float:
        return max(0.0, (self.entry - self.stop) * self.shares)


@dataclass
class PortfolioState:
    equity: float
    cash: float
    positions: List[OpenPosition] = field(default_factory=list)
    realized_today: float = 0.0
    realized_this_week: float = 0.0
    consecutive_losses: int = 0

    @property
    def heat(self) -> float:
        if self.equity <= 0:
            return 1.0
        return sum(p.open_risk for p in self.positions) / self.equity

    def exposure_by(self, attr: str) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for p in self.positions:
            out[getattr(p, attr)] = out.get(getattr(p, attr), 0.0) + p.market_value
        return {k: (v / self.equity if self.equity else 0.0) for k, v in out.items()}


@dataclass
class SizingResult:
    shares: int
    risk_amount: float
    stop: float
    notional: float
    reason: str

    @property
    def allowed(self) -> bool:
        return self.shares > 0


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def circuit_breaker(self, state: PortfolioState) -> Optional[str]:
        c = self.config
        if state.consecutive_losses >= c.consecutive_loss_circuit_breaker:
            return f"circuit breaker: {state.consecutive_losses} consecutive losses"
        if state.equity > 0 and state.realized_today / state.equity <= -c.max_daily_loss:
            return "daily loss limit reached — no new risk today"
        if state.equity > 0 and state.realized_this_week / state.equity <= -c.max_weekly_loss:
            return "weekly loss limit reached — no new risk this week"
        return None

    def can_open(self, state: PortfolioState, sector: str, country: str, ticker: str) -> Tuple[bool, str]:
        c = self.config
        halt = self.circuit_breaker(state)
        if halt:
            return False, halt
        if any(p.ticker == ticker for p in state.positions):
            return False, "duplicate position already open"
        if len(state.positions) >= c.max_concurrent_positions:
            return False, f"max concurrent positions ({c.max_concurrent_positions}) reached"
        if state.heat >= c.max_portfolio_heat:
            return False, f"portfolio heat {state.heat:.1%} at ceiling {c.max_portfolio_heat:.1%}"
        if state.exposure_by("sector").get(sector, 0.0) >= c.max_sector_exposure:
            return False, f"sector exposure limit reached for {sector}"
        if state.exposure_by("country").get(country, 0.0) >= c.max_country_exposure:
            return False, f"country exposure limit reached for {country}"
        return True, "risk checks passed"

    def size(self, state: PortfolioState, price: float, atr: float) -> SizingResult:
        """Risk-based sizing only. Never arbitrary share counts."""
        c = self.config
        stop = price - c.atr_stop_multiple * atr
        stop_distance = price - stop
        if stop_distance <= 0 or price <= 0:
            return SizingResult(0, 0.0, stop, 0.0, "invalid stop distance")

        budget = state.equity * c.max_risk_per_trade
        remaining_heat = max(0.0, c.max_portfolio_heat - state.heat) * state.equity
        risk_amount = min(budget, remaining_heat)
        if risk_amount <= 0:
            return SizingResult(0, 0.0, stop, 0.0, "no risk budget remaining under heat ceiling")

        shares = int(risk_amount // stop_distance)
        notional = shares * price
        if notional > state.cash:
            shares = int(state.cash // price)
            notional = shares * price
        if shares <= 0:
            return SizingResult(0, 0.0, stop, 0.0, "insufficient cash for a risk-compliant position")

        return SizingResult(
            shares=shares,
            risk_amount=round(shares * stop_distance, 2),
            stop=round(stop, 4),
            notional=round(notional, 2),
            reason=f"risking {shares * stop_distance:,.0f} ({(shares * stop_distance) / state.equity:.2%} of equity)",
        )
